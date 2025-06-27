message = ""

columns = [
    {"fieldname": "posting_date", "label": "Posting Date", "fieldtype": "Date", "width": 120},
    {"fieldname": "voucher_no", "label": "Voucher No", "fieldtype": "Data", "width": 200},
    {"fieldname": "against_account", "label": "Against / Account", "fieldtype": "Data", "width": 350},
    {"fieldname": "parent_account", "label": "Parent Account", "fieldtype": "Data", "width": 200},
    {"fieldname": "account", "label": "Account", "fieldtype": "Data", "width": 200},
    {"fieldname": "description", "label": "Remarks / Description", "fieldtype": "Data", "width": 480},
    {"fieldname": "expense", "label": "Expense", "fieldtype": "Currency", "width": 125},
    {"fieldname": "payments", "label": "Payments", "fieldtype": "Currency", "width": 125},
    {"fieldname": "receipts", "label": "Receipts", "fieldtype": "Currency", "width": 125},
]

posting_date = filters.get("posting_date")
parent_account = filters.get("parent_account")

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
            ecd.name AS ecd_name,
            acc.parent_account
        FROM `tabGL Entry` gl
        LEFT JOIN `tabExpense Claim Detail` ecd ON gl.voucher_no = ecd.parent
        LEFT JOIN `tabAccount` acc ON acc.name = gl.account
        WHERE
            gl.is_cancelled = 0
            AND gl.posting_date = %s
            AND (acc.parent_account = %s OR %s IS NULL)
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
        parent_account,
        account,
        description,
        ROUND(COALESCE(expense_amount, 0), 0) AS expense,
        CASE
            WHEN voucher_no LIKE 'HR-EXP%%' AND rn = 1 THEN ROUND(credit, 0)
            WHEN voucher_no LIKE 'HR-EXP%%' THEN 0
            ELSE ROUND(credit, 0)
        END AS payments,
        ROUND(debit, 0) AS receipts
    FROM numbered
    WHERE
        (voucher_no NOT LIKE 'HR-EXP%%' OR expense_amount IS NOT NULL)
    ORDER BY posting_date, parent_account, voucher_no, rn
""", (posting_date, parent_account, parent_account), as_dict=True)

# Totals
total_expense = sum(row.expense or 0 for row in result if row.voucher_no and row.voucher_no.startswith('HR-EXP'))
total_payments = sum(row.payments or 0 for row in result)
total_receipts = sum(row.receipts or 0 for row in result)

# Opening and Closing Balances
opening = frappe.db.sql("""
    SELECT COALESCE(SUM(debit) - SUM(credit), 0) AS balance
    FROM `tabGL Entry` gl
    LEFT JOIN `tabAccount` acc ON acc.name = gl.account
    WHERE gl.is_cancelled = 0
      AND gl.posting_date < %s
      AND (acc.parent_account = %s OR %s IS NULL)
""", (posting_date, parent_account, parent_account), as_dict=True)[0].balance or 0

closing = frappe.db.sql("""
    SELECT COALESCE(SUM(debit) - SUM(credit), 0) AS balance
    FROM `tabGL Entry` gl
    LEFT JOIN `tabAccount` acc ON acc.name = gl.account
    WHERE gl.is_cancelled = 0
      AND gl.posting_date <= %s
      AND (acc.parent_account = %s OR %s IS NULL)
""", (posting_date, parent_account, parent_account), as_dict=True)[0].balance or 0

def format_with_comma(val):
    try:
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
    except Exception as e:
        frappe.log_error(f"Error formatting value: {val} - {e}")
        return "0"

# Generate Summary
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

# Debug Logs
frappe.log_error("Cash Flow Statement - Intermediate Values:", {
    "opening": opening,
    "total_receipts": total_receipts,
    "total_payments": total_payments,
    "total_expense": total_expense,
    "closing": closing,
    "result_rows": len(result)
})
frappe.log_error("Cash Flow Statement - Summary:", str(summary))

data = columns, result, message, None, summary


-------------------------------------------------------------



Javascript


frappe.query_reports["Cash Flow Statement"] = {
  filters: [
    {
      fieldname: "posting_date",
      label: "Posting Date",
      fieldtype: "Date",
      default: frappe.datetime.get_today(),
      reqd: 1,
    },
    {
      fieldname: "parent_account",
      label: "Parent Account",
      fieldtype: "Link",
      options: "Account",
      get_query: function() {
        return {
          filters: {
            is_group: 1  // Only show group accounts as parent accounts
          }
        };
      }
    }
  ],
  onload: function(report) {
    // Add Print button outside view list
    if (!report.page.main_buttons || !report.page.main_buttons["Print"]) {
      report.page.add_button("Print", async () => {
        const filters = report.get_filter_values();
        if (!filters.posting_date) {
          frappe.throw(__("Please select a Posting Date"));
          return;
        }
        try {
          const result = await new Promise((resolve, reject) => {
            frappe.call({
              method: "frappe.desk.query_report.run",
              args: {
                report_name: "Cash Flow Statement",
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
          const summary = result.message.summary || [];
          let total_expense = 0, total_payments = 0, total_receipts = 0;
          data.forEach(row => {
            total_expense += parseFloat(row.expense || 0);
            total_payments += parseFloat(row.payments || 0);
            total_receipts += parseFloat(row.receipts || 0);
          });

          function format_number(val) {
            try {
              val = parseInt(val) || 0;
              let s = val.toString();
              if (s.length <= 3) return s;
              let parts = [];
              while (s.length > 3) {
                parts.unshift(s.slice(-3));
                s = s.slice(0, -3);
              }
              parts.unshift(s);
              return parts.join(",");
            } catch (e) {
              console.error("Error formatting number:", e);
              return "0";
            }
          }

          let summaryMap = {};
          if (summary && summary.length > 0) {
            summary.forEach(item => {
              if (item.label && item.value !== undefined) {
                summaryMap[item.label] = item.value.toString();
              } else {
                console.warn(`Invalid summary item: ${JSON.stringify(item)}`);
              }
            });
          } else {
            console.warn("Summary array is empty, computing fallback values from data");
            const openingBalanceRes = await frappe.call({
              method: "frappe.client.get_value",
              args: {
                doctype: "GL Entry",
                filters: {
                  is_cancelled: 0,
                  posting_date: ["<", filters.posting_date]
                },
                fieldname: "sum(debit) - sum(credit) as balance"
              }
            });
            const total_opening = openingBalanceRes.message?.balance || 0;

            const closingBalanceRes = await frappe.call({
              method: "frappe.client.get_value",
              args: {
                doctype: "GL Entry",
                filters: {
                  is_cancelled: 0,
                  posting_date: ["<=", filters.posting_date]
                },
                fieldname: "sum(debit) - sum(credit) as balance"
              }
            });
            const total_closing = closingBalanceRes.message?.balance || 0;

            summaryMap = {
              "Opening Balance": format_number(total_opening),
              "Today Receipts": format_number(total_receipts),
              "Total Balance": format_number(total_opening + total_receipts),
              "Net Cash Flow": format_number(total_receipts - total_payments),
              "Total Payments": format_number(total_payments),
              "Total Expense": format_number(total_expense),
              "Other Payments": format_number(total_payments - total_expense),
              "Closing Balance": format_number(total_closing)
            };
          }

          const requiredKeys = [
            "Opening Balance", "Today Receipts", "Total Balance", "Net Cash Flow",
            "Total Payments", "Total Expense", "Other Payments", "Closing Balance"
          ];
          requiredKeys.forEach(key => {
            if (!summaryMap[key]) {
              console.warn(`Missing summary key: ${key}`);
              summaryMap[key] = "0";
            }
          });

          const companyRes = await frappe.db.get_value("Company", { name: frappe.defaults.get_default("company") }, "*");
          const company = companyRes.message || {};
          const companyName = company.name || "";
          const logoUrl = company.logo ? company.logo : "/files/logo CCL.JPG";

          const balancesHtml = `
            <div style="margin-bottom: 20px; display: inline-block; vertical-align: top;">
              <table style="width: 300px; border-collapse: collapse; table-layout: fixed;">
                <thead><tr style="background-color: #f2f2f2;"><th colspan="2" style="border: 2px solid #0d0405; padding: 8px;">Opening Balance, Receipts & Cashflow</th></tr></thead>
                <tbody>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Opening Balance</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Opening Balance"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Today Receipts</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Today Receipts"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Total Balance</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Total Balance"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Net Cash Flow</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Net Cash Flow"]}</td></tr>
                </tbody>
              </table>
            </div>
          `;

          const summaryHtml = `
            <div style="margin-bottom: 20px; display: inline-block; vertical-align: top; margin-left: 20px;">
              <table style="width: 300px; border-collapse: collapse; table-layout: fixed;">
                <thead><tr style="background-color: #f2f2f2;"><th colspan="2" style="border: 2px solid #0d0405; padding: 8px;">Expenses, Payments & Closing Balance</th></tr></thead>
                <tbody>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Total Payments</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Total Payments"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Total Expense</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Total Expense"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Other Payments</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Other Payments"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 5px;">Closing Balance</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Closing Balance"]}</td></tr>
                </tbody>
              </table>
            </div>
          `;

          const html = `
            <html>
              <head>
                <title>Cash Flow Statement</title>
                <style>
                  @media print {
                    @page { size: landscape; margin: 10mm; }
                  }
                  body { font-family: sans-serif; font-size: 12px; margin: 10px; }
                  .header { display: flex; justify-content: space-between; align-items: center; }
                  .header-left { text-align: left; }
                  .header-right img { max-width: 70px; }
                  table {
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 12px;
                    margin-top: 5px;
                    table-layout: fixed;
                    word-wrap: break-word;
                  }
                  th, td {
                    border: 1px solid #444;
                    padding: 5px;
                    text-align: left;
                  }
                  th { background-color: #f8facf; font-weight: bold; }
                  ul { padding-left: 20px; }
                  .footer {
                    margin-top: 80px;
                    font-size: 12px;
                    color: black;
                    display: flex;
                    justify-content: space-between;
                  }
                  .footer-left, .footer-center, .footer-right {
                    width: 30%;
                    text-align: left;
                  }
                  .footer-center {
                    text-align: center;
                  }
                  .footer-right {
                    text-align: right;
                  }
                </style>
              </head>
              <body>
                <div class="header">
                  <div class="header-left">
                    <h2>${companyName}</h2>
                    <p><strong>Posting Date:</strong> ${filters.posting_date}</p>
                    <p><strong>Parent Account:</strong> ${filters.parent_account || "All"}</p>
                  </div>
                  <div class="header-right">
                    <img src="${logoUrl}" alt="Company Logo">
                  </div>
                </div>
                <hr>
                ${balancesHtml}
                ${summaryHtml}
                <h2>Detailed Ledger Transactions Report</h2>
                <table>
                  <thead>
                    <tr>
                      <th style="width: 100px;">Posting Date</th>
                      <th style="width: 130px;">Voucher No</th>
                      <th style="width: 180px;">Against / Account</th>
                      <th style="width: 200px;">Parent Account</th>
                      <th style="width: 200px;">Account</th>
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
                        <td>${row.parent_account || ""}</td>
                        <td>${row.account || ""}</td>
                        <td>${row.description || ""}</td>
                        <td style="text-align:right;">${format_number(row.expense)}</td>
                        <td style="text-align:right;">${format_number(row.payments)}</td>
                        <td style="text-align:right;">${format_number(row.receipts)}</td>
                      </tr>
                    `).join("")}
                  </tbody>
                </table>

                <!-- Total Row Moved Outside Table -->
                <table style="margin-top: -1px;">
                  <tfoot>
                    <tr>
                      <th colspan="6" style="text-align:right;">Total</th>
                      <th style="text-align:right;">${format_number(total_expense)}</th>
                      <th style="text-align:right;">${format_number(total_payments)}</th>
                      <th style="text-align:right;">${format_number(total_receipts)}</th>
                    </tr>
                  </tfoot>
                </table>

                <!-- Footer Section -->
                <div class="footer">
                  <div class="footer-left">
                    <strong>Created By:</strong><br>
                    ${frappe.session.user}
                  </div>
                  <div class="footer-center">
                    <strong>Submitted By:</strong><br>
                    Accountant
                  </div>
                  <div class="footer-right">
                    <strong>Approved By:</strong><br>
                    Director
                  </div>
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
      });
      // Prevent duplicate buttons
      if (!report.page.main_buttons) report.page.main_buttons = {};
      report.page.main_buttons["Print"] = true;
    }
  }
};
