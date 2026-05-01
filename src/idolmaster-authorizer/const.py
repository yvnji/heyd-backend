import os


AWS_REGION_SEOUL = "ap-northeast-2"
AWS_REGION_VIRGINIA = "us-east-1"

ALIAS_DEV = "dev"
ALIAS_STAGE = "staging"
ALIAS_PROD = "prod"

COGNITO_CLIENT_ID = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: "3mialbi12jbfgqgqhbpm3jbut9",
        ALIAS_STAGE: "4mpakd5pb8u33u5a2akggreq01"
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: "vaspnmsmdkjvvoqf31ps79865",
        ALIAS_STAGE: "9gn66ouvi0lr39s9safauhmjk",
        ALIAS_PROD: "7org7pa5t7ie76apsh9s3misuj"
    }
}
COGNITO_USER_POOL_ID = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: "ap-northeast-2_FsdIftHTU",
        ALIAS_STAGE: "ap-northeast-2_lD3G3dbVt"
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: "us-east-1_WKus2hFbb",
        ALIAS_STAGE: "us-east-1_QJBjGWJnP",
        ALIAS_PROD: "us-east-1_Gpunfo08I"
    }
}

SQL_DB_NAME = "idolmaster"

SQL_DB_HOST = {
    AWS_REGION_SEOUL: {
        ALIAS_DEV: os.environ["SQL_DB_HOST_SEOUL_DEV"],
        ALIAS_STAGE: os.environ["SQL_DB_HOST_SEOUL_STAGING"],
    },
    AWS_REGION_VIRGINIA: {
        ALIAS_DEV: os.environ["SQL_DB_HOST_VIRGINIA_DEV"],
        ALIAS_STAGE: os.environ["SQL_DB_HOST_VIRGINIA_STAGING"],
        ALIAS_PROD: os.environ["SQL_DB_HOST_VIRGINIA_PROD"],
    },
}
SQL_DB_PORT = int(os.environ["SQL_DB_PORT"])
SQL_DB_USER = {
    ALIAS_DEV: os.environ["SQL_DB_USER_DEV"],
    ALIAS_STAGE: os.environ["SQL_DB_USER_STAGING"],
    ALIAS_PROD: os.environ["SQL_DB_USER_PROD"],
}
SQL_DB_PASSWORD = {
    ALIAS_DEV: os.environ["SQL_DB_PASSWORD_DEV"],
    ALIAS_STAGE: os.environ["SQL_DB_PASSWORD_STAGING"],
    ALIAS_PROD: os.environ["SQL_DB_PASSWORD_PROD"],
}
