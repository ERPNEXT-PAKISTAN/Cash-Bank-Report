message = "Cash Report"

columns = [
    _("Posting Date") + ":Date:120",
    _("Voucher No") + "::195",
    _("Against / Account") + "::250",
    _("Remarks / Description") + "::350",
    _("Expense Amount") + ":Currency:120",
    _("Payments") + ":Currency:120",
    _("Receipts") + ":Currency:120",
]

posting_date = filters.get("posting_date")
account = filters.get("account")

# ✅ Main Data Query
mydata = frappe.db.sql("""
    WITH Combined AS (
        SELECT
            gl.posting_date AS `Posting Date`,
            gl.voucher_no AS `Voucher No`,
            gl.account AS `Account`,
            CONCAT_WS(' / ', gl.against, ecd.default_account) AS `Against / Account`,
            CONCAT_WS(' | ',
                COALESCE(gl.remarks, ''),
                COALESCE(REGEXP_REPLACE(ecd.description, '<[^>]*>', ''), '')
            ) AS `Remarks / Description`,
            ecd.amount AS `Expense Amount`,
            gl.debit AS `Total Debit`,
            gl.credit AS `Total Credit`,
            ROW_NUMBER() OVER (PARTITION BY gl.voucher_no ORDER BY COALESCE(ecd.name, '')) AS rn
        FROM
            `tabGL Entry` gl
        LEFT JOIN
            `tabExpense Claim Detail` ecd ON gl.voucher_no = ecd.parent
        WHERE
            gl.is_cancelled = 0
            AND gl.account = %s
            AND gl.posting_date = %s
    )
    SELECT
        `Posting Date`,
        `Voucher No`,
        `Against / Account`,
        `Remarks / Description`,
        `Expense Amount`,
        CASE WHEN rn = 1 THEN `Total Credit` ELSE NULL END AS `Payments`,
        CASE WHEN rn = 1 THEN `Total Debit` ELSE NULL END AS `Receipts`
    FROM
        Combined
    ORDER BY
        `Posting Date`, `Voucher No`
""", (account, posting_date), as_list=1)

# ✅ Summary Totals
total_expense = sum(row[4] or 0 for row in mydata)
total_payments = sum(row[5] or 0 for row in mydata)
total_receipts = sum(row[6] or 0 for row in mydata)

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

# ✅ Comma formatting function (safe in script reports)
def format_no_decimal(val):
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

# ✅ Summary with comma-separated numbers
summary = [
    {"label": "Opening Balance", "value": format_no_decimal(opening), "indicator": "Orange"},
    {"label": "Total Expense Amount", "value": format_no_decimal(total_expense), "indicator": "Red"},
    {"label": "Total Payments", "value": format_no_decimal(total_payments), "indicator": "Blue"},
    {"label": "Total Receipts", "value": format_no_decimal(total_receipts), "indicator": "Green"},
    {"label": "Closing Balance", "value": format_no_decimal(closing), "indicator": "Green"},
]

data = columns, mydata, message, None, summary


-------------------------------------

# Add in Filter with Printable Button--

Javascript

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
            <div style="padding: 20px; font-family: sans-serif;">
              <h2>Cash & Bank Report</h2>
              <p><strong>Posting Date:</strong> ${filters.posting_date}</p>
              <p><strong>Account:</strong> ${filters.account}</p>
              <br>
              <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <thead>
                  <tr>
                    <th>Posting Date</th>
                    <th>Voucher No</th>
                    <th>Against / Account</th>
                    <th>Remarks / Description</th>
                    <th>Expense</th>
                    <th>Payments</th>
                    <th>Receipts</th>
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

              <br><h3>Summary</h3>
              <ul>
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




