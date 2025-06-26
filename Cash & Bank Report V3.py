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
    // Add Printable HTML button only once
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
          const summary = result.message.summary || [];

          // Log for debugging
          console.log("Full Result:", JSON.stringify(result, null, 2));
          console.log("Summary:", summary);
          console.log("Data:", data);

          // Compute totals from data for the detailed ledger table and fallback summary
          let total_expense = 0, total_payments = 0, total_receipts = 0;
          data.forEach(row => {
            total_expense += parseFloat(row.expense || 0);
            total_payments += parseFloat(row.payments || 0);
            total_receipts += parseFloat(row.receipts || 0);
          });

          // Format number to match Python's format_with_comma
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

          // Extract summary values or compute fallback
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
            // Fetch opening and closing balances from backend
            const openingBalanceRes = await frappe.call({
              method: "frappe.client.get_value",
              args: {
                doctype: "GL Entry",
                filters: {
                  is_cancelled: 0,
                  account: filters.account,
                  posting_date: ["<", filters.posting_date]
                },
                fieldname: "sum(debit) - sum(credit) as balance"
              }
            });
            const opening = openingBalanceRes.message?.balance || 0;

            const closingBalanceRes = await frappe.call({
              method: "frappe.client.get_value",
              args: {
                doctype: "GL Entry",
                filters: {
                  is_cancelled: 0,
                  account: filters.account,
                  posting_date: ["<=", filters.posting_date]
                },
                fieldname: "sum(debit) - sum(credit) as balance"
              }
            });
            const closing = closingBalanceRes.message?.balance || 0;

            // Build fallback summary
            summaryMap = {
              "Opening Balance": format_number(opening),
              "Today Receipts": format_number(total_receipts),
              "Total Balance": format_number(opening + total_receipts),
              "Net Cash Flow": format_number(total_receipts - total_payments),
              "Total Payments": format_number(total_payments),
              "Total Expense": format_number(total_expense),
              "Other Payments": format_number(total_payments - total_expense),
              "Closing Balance": format_number(closing)
            };
          }

          // Verify required summary keys
          const requiredKeys = [
            "Opening Balance",
            "Today Receipts",
            "Total Balance",
            "Net Cash Flow",
            "Total Payments",
            "Total Expense",
            "Other Payments",
            "Closing Balance"
          ];
          requiredKeys.forEach(key => {
            if (!summaryMap[key]) {
              console.warn(`Missing summary key: ${key}`);
              summaryMap[key] = "0";
            }
          });

          // Fetch company info
          const companyRes = await frappe.db.get_value("Company", { name: frappe.defaults.get_default("company") }, "*");
          const company = companyRes.message || {};
          const companyName = company.name || "";
          const logoUrl = company.logo ? company.logo : "/files/logo CCL.JPG";

          // Build two Summary Tables (300px each)
          const balancesHtml = `
            <div style="margin-bottom: 20px; display: inline-block; vertical-align: top;">
              <table style="width: 300px; border-collapse: collapse; table-layout: fixed;">
                <thead>
                  <tr style="background-color: #f2f2f2;">
                    <th colspan="2" style="border: 2px solid #0d0405; padding: 8px;">Opening Balance,  Receipts & Cashflow</th>
                  </tr>
                </thead>
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
                <thead>
                  <tr style="background-color: #f2f2f2;">
                    <th colspan="2" style="border: 2px solid #0d0405; padding: 8px;">Expenses, Payments & Closing Balance</th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td style="border: 1px solid #050000; padding: 6px;">Total Payments</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Total Payments"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 6px;">Total Expense</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Total Expense"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 6px;">Other Payments</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Other Payments"]}</td></tr>
                  <tr><td style="border: 1px solid #050000; padding: 6px;">Closing Balance</td><td style="border: 1px solid #050000; padding: 6px; text-align: right;">${summaryMap["Closing Balance"]}</td></tr>
                </tbody>
              </table>
            </div>
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
                  th { background-color: #f8facf; }
                  ul { padding-left: 20px; }
                  .footer {
                    margin-top: 50px;
                    text-align: center;
                    font-size: 10px;
                    color: #e1f7f7;
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

                ${balancesHtml}
                ${summaryHtml}

                <h2>Detailed Ledger Transactions Report</h2>
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
                      <th style="text-align:right;">${format_number(total_payments)}</th>
                      <th style="text-align:right;">${format_number(total_receipts)}</th>
                    </tr>
                  </tfoot>
                </table>

                <div class="footer">
                  Generated on ${frappe.datetime.nowdate()} — Powered by Tech Craft Pvt Ltd
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
