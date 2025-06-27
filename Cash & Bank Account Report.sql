WITH GL_Summary AS (
  SELECT
    gl.`posting_date` AS `Posting Date`,
    gl.`voucher_no` AS `Voucher No`,
    gl.`account` AS `Account`,
    gl.`against` AS `Against`,
    gl.`remarks` AS `Remarks`,
    gl.`debit` AS `Total Debit`,
    gl.`credit` AS `Total Credit`,
    ecd.`parent` AS `Expense Parent`,
    ecd.`default_account` AS `Default Account`,
    REGEXP_REPLACE(ecd.`description`, '<[^>]*>', '') AS `Description`,
    ecd.`amount` AS `Expense Amount`,
    ecd.`name` AS `Expense Detail Name`
  FROM
    `tabGL Entry` gl
  LEFT JOIN
    `tabExpense Claim Detail` ecd
    ON gl.`voucher_no` = ecd.`parent`
  WHERE
    gl.`posting_date` <= %(end_date)s
    AND (%(account)s IS NULL OR gl.`account` = %(account)s)
    AND gl.`company` = %(company)s
    AND gl.`is_cancelled` = 0
),

Filtered_GL_Summary AS (
  SELECT
    *,
    CONCAT_WS(' / ', `Against`, `Default Account`) AS `Against / Account`,
    CONCAT_WS(' | ', `Remarks`, `Description`) AS `Remarks / Description`
  FROM
    GL_Summary
  WHERE
    `Posting Date` BETWEEN %(start_date)s AND %(end_date)s
),

Numbered_Rows AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY `Voucher No` ORDER BY `Expense Detail Name`) AS rn
  FROM
    Filtered_GL_Summary
)

SELECT
  `Posting Date`,
  `Voucher No`,
  `Against / Account`,
  `Remarks / Description`,
  `Expense Amount`,
  CASE 
    WHEN rn = 1 THEN 
      CASE 
        WHEN `Voucher No` LIKE 'HR-EXP%%' THEN `Total Credit`
        ELSE `Total Credit`
      END
    WHEN `Voucher No` LIKE 'HR-EXP%%' THEN NULL
    ELSE `Total Credit`
  END AS `Payments`,
  `Total Debit` AS `Receipts`
FROM
  Numbered_Rows
ORDER BY
  `Posting Date` ASC,
  `Voucher No` ASC;


================================
Filters:



  


================================
Columns:




