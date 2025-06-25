message = []
columns = [
    {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date", "width": 120},
    {"fieldname": "voucher_no", "label": "Voucher No", "fieldtype": "Data", "width": 200},
    {"fieldname": "against_account", "label": "Against / Account", "fieldtype": "Data", "width": 350},
    {"fieldname": "description", "label": "Remarks / Description", "fieldtype": "Data", "width": 480},
    {"fieldname": "expense", "label": "Expense", "fieldtype": "Currency", "width": 125},
    {"fieldname": "payments", "label": "Payments", "fieldtype": "Currency", "width": 125},
    {"fieldname": "receipts", "label": "Receipts", "fieldtype": "Currency", "width": 125},
]

posting_date = filters.get("posting_date")
account = filters.get("account")

result = frappe.db.sql("""
    WITH gl_data AS (
        SELECT
            gl.posting_date,
            gl.voucher_no,
            gl.account,
            gl.against,
            gl.remarks,
            gl.debit,
            gl.credit,
            ecd.default_account,
            ecd.amount AS expense_amount,
            REGEXP_REPLACE(ecd.description, '<[^>]*>', '') AS ecd_description,
            ecd.name AS ecd_name
        FROM `tabGL Entry` gl
        LEFT JOIN `tabExpense Claim Detail` ecd ON gl.voucher_no = ecd.parent
        WHERE
            gl.is_cancelled = 0
            AND gl.account = %s
            AND gl.posting_date = %s
    ),

    numbered AS (
        SELECT *,
            CONCAT_WS(' / ', against, default_account) AS against_account,
            CONCAT_WS(' | ', remarks, ecd_description) AS description,
            ROW_NUMBER() OVER (
                PARTITION BY voucher_no
                ORDER BY ecd_name
            ) AS rn
        FROM gl_data
    )

    SELECT
        posting_date,
        voucher_no,
        against_account,
        description,
        -- show each expense detail row
        ROUND(COALESCE(expense_amount, 0), 0) AS expense,
        -- show payment only once per expense claim
        CASE
            WHEN voucher_no LIKE 'HR-EXP%%' AND rn = 1 THEN ROUND(credit, 0)
            WHEN voucher_no LIKE 'HR-EXP%%' THEN 0
            ELSE ROUND(credit, 0)
        END AS payments,
        ROUND(debit, 0) AS receipts
    FROM numbered
    ORDER BY posting_date, voucher_no, rn
""", (account, posting_date), as_dict=True)

# Totals
total_expense = sum(row.expense or 0 for row in result)
total_payments = sum(row.payments or 0 for row in result)
total_receipts = sum(row.receipts or 0 for row in result)

# Opening and Closing Balances
opening = frappe.db.sql("""
    SELECT COALESCE(SUM(debit) - SUM(credit), 0) AS balance
    FROM `tabGL Entry`
    WHERE is_cancelled = 0
      AND account = %s
      AND posting_date < %s
""", (account, posting_date), as_dict=True)[0].balance or 0

closing = frappe.db.sql("""
    SELECT COALESCE(SUM(debit) - SUM(credit), 0) AS balance
    FROM `tabGL Entry`
    WHERE is_cancelled = 0
      AND account = %s
      AND posting_date <= %s
""", (account, posting_date), as_dict=True)[0].balance or 0

def format_with_comma(val):
    val = int(val)
    s = str(val)
    if len(s) <= 3:
        return s
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    parts.insert(0, s)
    return ",".join(parts)

summary = [
    {"label": "Opening Balance", "value": format_with_comma(opening), "indicator": "Orange"},
    {"label": "Today Receipts", "value": format_with_comma(total_receipts), "indicator": "Green"},
    {"label": "Total Balance", "value": format_with_comma(opening + total_receipts), "indicator": "Blue"},
    {"label": "Total Expense", "value": format_with_comma(total_expense), "indicator": "Red"},
    {"label": "Other Payments", "value": format_with_comma(total_payments - total_expense), "indicator": "Red"},
    {"label": "Total Payments", "value": format_with_comma(total_payments), "indicator": "Red"},
    {"label": "Closing Balance", "value": format_with_comma(closing), "indicator": "Green"},
    
]


data = columns, result, message, None, summary, None

-----------------------------



# Add in Client Script for Filter & View
Javascript

frappe.query_reports["Cash & Bank Report"] = {
  filters: [
    {
      fieldname: "posting_date",
      label: "Posting Date",
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
      reqd: 1,
    },
    {
      fieldname: "account",
      label: "Account",
      fieldtype: "Select",
      options: [
        "Cash with Anam - CCL",
        "Cash with Azhar - CCL",
        "Cash with Boota - CCL",
        "Cash with Khalil - CCL",
        "Cash with Salman Sarwar - CCL",
        "Cash with Suwaib - CCL",
        "MBL 0103525749 - CCL",
        "Bank Clearance - CCL",
        "MBL Abdul Rehman - 083 - CCL",
        "MBL Abdul Rehman - CCL",
        "MBL Rutab Ahmad - CCL"
      ],
      default: "Cash with Anam - CCL",
      reqd: 1
    }
  ],

  onload: function (report) {
    report.page.add_inner_button("Printable HTML", function () {
      const filters = report.get_filter_values();

      // Step 1: Get company name and logo
      frappe.call({
        method: "frappe.client.get",
        args: {
          doctype: "Company",
          name: frappe.defaults.get_default("company")
        },
        callback: function (company_res) {
          const company = company_res.message || {};
          const company_name = company.name || "";
          const logo_url = company.logo ? company.logo : "/assets/erpnext/images/erpnext-logo.svg";

          // Step 2: Run report data
          frappe.call({
            method: "frappe.desk.query_report.run",
            args: {
              report_name: "Cash & Bank Report",
              filters: filters
            },
            callback: function (r) {
              const data = r.message.result || [];
              const summary = r.message.summary || [];

              // Step 3: Build HTML
              const html = `
                <html>
                  <head>
                    <title>Cash & Bank Report</title>
                    <style>
                      body { font-family: sans-serif; font-size: 12px; margin: 40px; }
                      .header { display: flex; justify-content: space-between; align-items: center; }
                      .header-left { text-align: left; }
                      .header-right img { max-width: 150px; }
                      table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 20px; }
                      th, td { border: 1px solid #444; padding: 5px; }
                      th { background-color: #f0f0f0; }
                      ul { padding-left: 20px; }
                      .footer { margin-top: 50px; text-align: center; font-size: 10px; color: #888; }
                    </style>
                  </head>
                  <body>
                    <div class="header">
                      <div class="header-left">
                        <h2>${company_name}</h2>
                        <p><strong>Posting Date:</strong> ${filters.posting_date}</p>
                        <p><strong>Account:</strong> ${filters.account}</p>
                      </div>
                      <div class="header-right">
                        <img src="${logo_url}" alt="Company Logo">
                      </div>
                    </div>

                    <hr>

                    <table>
                      <thead>
                        <tr>
                          <th style="width: 100px;">Posting Date</th>
                          <th style="width: 130px;">Voucher No</th>
                          <th style="width: 180px;">Against / Account</th>
                          <th style="width: 250px;">Remarks / Description</th>
                          <th style="width: 90px;">Expense</th>
                          <th style="width: 90px;">Payments</th>
                          <th style="width: 90px;">Receipts</th>
                        </tr>
                      </thead>
                      <tbody>
                        ${data.map(row => `
                          <tr>
                            <td>${row.posting_date || ""}</td>
                            <td>${row.voucher_no || ""}</td>
                            <td>${row.against_account || ""}</td>
                            <td>${row.description || ""}</td>
                            <td style="text-align:right;">${format_number(row.expense)}</td>
                            <td style="text-align:right;">${format_number(row.payments)}</td>
                            <td style="text-align:right;">${format_number(row.receipts)}</td>
                          </tr>
                        `).join("")}
                      </tbody>
                    </table>

                    <h3 style="margin-top: 30px;">Summary</h3>
                    <ul>
                      ${summary.map(s => `<li><strong>${s.label}:</strong> ${s.value}</li>`).join("")}
                    </ul>

                    <div class="footer">
                      Generated on ${frappe.datetime.nowdate()} — Powered by ERPNext
                    </div>
                  </body>
                </html>
              `;

              const newTab = window.open("", "_blank");
              newTab.document.write(html);
              newTab.document.close();

              // Optional: Auto open print dialog
              newTab.onload = function () {
                newTab.print();
              };
            }
          });
        }
      });

      // Format numbers with comma
      function format_number(val) {
        val = val || 0;
        return parseFloat(val).toLocaleString("en-PK", { maximumFractionDigits: 0 });
      }
    });

    // Excel Export
    report.page.add_inner_button("Export Excel", function () {
      frappe.query_report.export_report("Cash & Bank Report", "Excel", report.get_filter_values());
    });
  }
};

