message = "Cash with Anam"

columns = [
    _("Posting Date") + ":Date:120",
    _("Voucher No") + "::195",
    _("Against / Account") + "::200",
    _("Remarks / Description") + "::250",
    _("Expense Amount") + ":Currency:120",
    _("Payments") + ":Currency:120",
    _("Receipts") + ":Currency:120",
]

posting_date = filters.get("posting_date") if filters else None

# ✅ Main Data Query
mydata = frappe.db.sql("""
    WITH Combined AS (
        SELECT
            gl.`posting_date` AS `Posting Date`,
            gl.`voucher_no` AS `Voucher No`,
            gl.`account` AS `Account`,
            CONCAT_WS(' / ', gl.`against`, ecd.`default_account`) AS `Against / Account`,
            CONCAT_WS(' | ', gl.`remarks`, REGEXP_REPLACE(ecd.`description`, '<[^>]*>', '')) AS `Remarks / Description`,
            ecd.`amount` AS `Expense Amount`,
            gl.`debit` AS `Total Debit`,
            gl.`credit` AS `Total Credit`,
            ROW_NUMBER() OVER (PARTITION BY gl.`voucher_no` ORDER BY ecd.`name`) AS rn
        FROM
            `tabGL Entry` gl
        LEFT JOIN
            `tabExpense Claim Detail` ecd
            ON gl.`voucher_no` = ecd.`parent`
        WHERE
            gl.`is_cancelled` = 0
            AND gl.`account` = "Cash with Anam - CCL"
            AND gl.`posting_date` = %s
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
""", (posting_date,), as_list=1)

# ✅ Calculate Summary
total_expense = sum(row[4] or 0 for row in mydata)
total_payments = sum(row[5] or 0 for row in mydata)
total_receipts = sum(row[6] or 0 for row in mydata)

# ✅ Opening & Closing Balance Calculation
opening = frappe.db.sql("""
    SELECT SUM(debit) - SUM(credit) AS balance
    FROM `tabGL Entry`
    WHERE `is_cancelled` = 0
      AND `account` = "Cash with Anam - CCL"
      AND `posting_date` < %s
""", (posting_date,), as_dict=True)[0].balance or 0

closing = frappe.db.sql("""
    SELECT SUM(debit) - SUM(credit) AS balance
    FROM `tabGL Entry`
    WHERE `is_cancelled` = 0
      AND `account` = "Cash with Anam - CCL"
      AND `posting_date` <= %s
""", (posting_date,), as_dict=True)[0].balance or 0

# ✅ Full Summary Section
summary = [
    {"label": f"Opening Balance", "value": opening, "indicator": "Orange"},
    {"label": "Total Expense Amount", "value": total_expense, "indicator": "Red"},
    {"label": "Total Payments", "value": total_payments, "indicator": "Blue"},
    {"label": "Total Receipts", "value": total_receipts, "indicator": "Green"},
    {"label": f"Closing Balance", "value": closing, "indicator": "Green"},
]

# ✅ Return Final Output
data = columns, mydata, message, None, summary




# add in Filters
Javascript

frappe.query_reports["Cash With Anam2"] = {
  filters: [
    {
      fieldname: "posting_date",
      label: "Posting Date",
      fieldtype: "Date",
      default: frappe.datetime.get_today()
    }
  ]
};
