SELECT 
    name, 
    account_type,
    account_name
FROM 
    tabAccount 
WHERE 
    account_type = %(account_type)s;



==============================
#//Set Filters:
    {
        'label': 'Account',        
        'fieldtype': 'Select',
        'fieldname': 'account_type',
        'options': 'Cash, Bank',
        'default': 'Cash',
    }

/////////////////////////////
#//Column Size:
    {
        'fieldname': 'name',
        'label': 'Name',
        'fieldtype': 'Data',
        'options': '',
        'width': 400
    }

    {
        'fieldname': 'account_type',
        'label': 'Account Type',
        'fieldtype': 'Data',
        'options': '',
        'width': 120
    }
    {
        'fieldname': 'account_name',
        'label': 'Account Name',
        'fieldtype': 'Data',
        'options': '',
        'width': 500
    }
--------------
