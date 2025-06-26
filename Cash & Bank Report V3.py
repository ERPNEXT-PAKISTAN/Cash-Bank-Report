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
    {"label": "Net Cash Flow", "value": format_with_comma(total_receipts - total_payments), "indicator": "Blue"},
    {"label": "Total Payments", "value": format_with_comma(total_payments), "indicator": "Red"},
    {"label": "Total Expense", "value": format_with_comma(total_expense), "indicator": "Red"},
    {"label": "Other Payments", "value": format_with_comma(total_payments - total_expense), "indicator": "Red"},
    {"label": "Closing Balance", "value": format_with_comma(closing), "indicator": "Green"},
]



data = columns, result, message, None, summary

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

  onload: function(report) {
    // Add Printable HTML button once
    if (!report.page.inner_toolbar_buttons || !report.page.inner_toolbar_buttons["Printable HTML"]) {
      report.page.add_inner_button("Printable HTML", async () => {
        const filters = report.get_filter_values();

        if (!filters.posting_date || !filters.account) {
          frappe.throw(__("Please select both Posting Date and Account"));
          return;
        }

        try {
          // Run the report
          const result = await new Promise((resolve, reject) => {
            frappe.call({
              method: "frappe.desk.query_report.run",
              args: {
                report_name: "Cash & Bank Report",
                filters: filters
              },
              callback: function(r) {
                if (r.exc) {
                  reject(r.exc);
                } else {
                  resolve(r);
                }
              }
            });
          });

          const data = result.message.result || [];

          // Compute totals
          let total_debit = 0;
          let total_credit = 0;
          let total_expense = 0;

          data.forEach(row => {
            total_debit += row.receipts || 0;
            total_credit += row.payments || 0;
            total_expense += row.expense || 0;
          });

          // Simulate Opening Balance (from previous rows in dataset)
          const openingBalance = (result.message.opening_balance || 0);

          const closingBalance = openingBalance + total_debit - total_credit;
          const netCashFlow = total_debit - total_credit;

          // Format number
          function format_number(val) {
            val = val || 0;
            return parseFloat(val).toLocaleString("en-PK", { maximumFractionDigits: 0 });
          }

          // Get company info
          const companyRes = await frappe.db.get_value("Company", { name: frappe.defaults.get_default("company") }, "*");
          const company = companyRes.message || {};
          const companyName = company.name || "";
          const logoUrl = company.logo ? company.logo : "/assets/erpnext/images/erpnext-logo.svg";

          // Build Summary Table
          const summaryHtml = `
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
              <thead>
                <tr style="background-color: #f2f2f2;">
                  <th style="border: 1px solid #ccc; padding: 8px;">Summary</th>
                  <th style="border: 1px solid #ccc; padding: 8px;">Value</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Opening Balance</td><td>${format_number(openingBalance)}</td></tr>
                <tr><td>Today Receipts</td><td>${format_number(total_debit)}</td></tr>
                <tr><td>Total Balance</td><td>${format_number(openingBalance + total_debit)}</td></tr>
                <tr><td>Net Cash Flow</td><td>${format_number(netCashFlow)}</td></tr>
                <tr><td>Total Payments</td><td>${format_number(total_credit)}</td></tr>
                <tr><td>Total Expense</td><td>${format_number(total_expense)}</td></tr>
                <tr><td>Other Payments</td><td>${format_number(total_credit - total_expense)}</td></tr>
                <tr><td>Closing Balance</td><td>${format_number(closingBalance)}</td></tr>
              </tbody>
            </table>
          `;

          // Generate Printable HTML
          const html = `
            <html>
              <head>
                <title>Cash & Bank Report</title>
                <style>
                  @media print {
                    @page { size: landscape; margin: 10mm; }
                  }
                  body { font-family: sans-serif; font-size: 12px; margin: 20px; }
                  .header { display: flex; justify-content: space-between; align-items: center; }
                  .header-left { text-align: left; }
                  .header-right img { max-width: 150px; }
                  table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                    margin-top: 20px;
                    table-layout: fixed;
                    word-wrap: break-word;
                  }
                  th, td {
                    border: 1px solid #444;
                    padding: 5px;
                    text-align: left;
                  }
                  th { background-color: #f0f0f0; }
                  ul { padding-left: 20px; }
                  .footer {
                    margin-top: 50px;
                    text-align: center;
                    font-size: 10px;
                    color: #888;
                  }
                </style>
              </head>
              <body>
                <div class="header">
                  <div class="header-left">
                    <h2>${companyName}</h2>
                    <p><strong>Posting Date:</strong> ${filters.posting_date}</p>
                    <p><strong>Account:</strong> ${filters.account}</p>
                  </div>
                  <div class="header-right">
                    <img src="${logoUrl}" alt="Company Logo">
                  </div>
                </div>

                <hr>

                <h3>Summary</h3>
                ${summaryHtml}

                <h3>Detailed Transactions</h3>
                <table>
                  <thead>
                    <tr>
                      <th style="width: 100px;">Posting Date</th>
                      <th style="width: 130px;">Voucher No</th>
                      <th style="width: 180px;">Against / Account</th>
                      <th style="width: 250px;">Description</th>
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
                  <tfoot>
                    <tr>
                      <th colspan="4" style="text-align:right;">Total</th>
                      <th style="text-align:right;">${format_number(total_expense)}</th>
                      <th style="text-align:right;">${format_number(total_credit)}</th>
                      <th style="text-align:right;">${format_number(total_debit)}</th>
                    </tr>
                  </tfoot>
                </table>

                <div class="footer">
                  Generated on ${frappe.datetime.nowdate()} — Powered by ERPNext
                </div>
              </body>
            </html>
          `;

          const newTab = window.open("", "_blank");
          newTab.document.write(html);
          newTab.document.close();

          newTab.onload = function () {
            newTab.print();
          };

        } catch (err) {
          console.error("Error generating printable report:", err);
          frappe.throw(__("Failed to generate Printable HTML. Please check browser console."));
        }
      }, __("View"), true);

      // Prevent duplicate buttons
      if (!report.page.inner_toolbar_buttons) report.page.inner_toolbar_buttons = {};
      report.page.inner_toolbar_buttons["Printable HTML"] = true;
    }
  }
};
