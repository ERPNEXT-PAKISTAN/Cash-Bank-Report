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

-----------------------------------------------


frappe.query_reports["Cash & Bank Report"] = {
  filters: [
    {
      fieldname: "posting_date",
      label: "Posting Date",
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
      reqd: 1
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
      frappe.call({
        method: "frappe.desk.query_report.run",
        args: {
          report_name: "Cash & Bank Report",
          filters: filters
        },
        callback: function (r) {
          const data = r.message.result || [];
          const summary = r.message.summary || [];

          const html = `
            <div style="padding: 20px; font-family: sans-serif; font-size: 12px;">
              <h2 style="font-size: 16px;">Cash & Bank Report</h2>
              <p><strong>Posting Date:</strong> ${filters.posting_date}</p>
              <p><strong>Account:</strong> ${filters.account}</p>
              <br>
              <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; width: 100%; font-size: 12px;">
                <thead>
                  <tr>
                    <th>Posting Date</th>
                    <th>Voucher No</th>
                    <th>Against / Account</th>
                    <th>Remarks / Description</th>
                    <th style="text-align:right;">Expense</th>
                    <th style="text-align:right;">Payments</th>
                    <th style="text-align:right;">Receipts</th>
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

              <br><h3 style="font-size: 14px;">Summary</h3>
              <ul style="font-size: 12px;">
                ${summary.map(s => `<li><strong>${s.label}:</strong> ${format_number(s.value)}</li>`).join("")}
              </ul>
            </div>
          `;

          const newWindow = window.open();
          newWindow.document.write(html);
          newWindow.document.close();
        }
      });

      function format_number(val) {
        val = val || 0;
        return parseFloat(val).toLocaleString("en-PK", { maximumFractionDigits: 0 });
      }
    });
  }
};
