import time

import mysql.connector


class Table:
    NAME = 'ignored_list'
    ID = 'id'
    FILENAME = 'filename'
    SIZE = 'size'
    COUNT = 'count'
    CREATED_AT = 'created_at'
    LAST_VIEWED_AT = 'last_viewed_at'


class IgnoreListDb:
    def __init__(self):
        def read_from_file(path: str):
            with open(path) as f:
                return f.read().strip('\n')

        self.database = mysql.connector.connect(
            host="localhost",
            user=read_from_file('db_user.pv'),
            password=read_from_file('db_password.pv'),
            database=read_from_file('db_name.pv')
        )

    def create_table(self):
        cursor = self.database.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS %s (" % Table.NAME +
                       "%s INT(6) UNSIGNED AUTO_INCREMENT PRIMARY KEY," % Table.ID +
                       "%s VARCHAR(250) NOT NULL PRIMARY KEY, " % Table.FILENAME +
                       "%s INT UNSIGNED DEFAULT 0, " % Table.SIZE +
                       "%s INT UNSIGNED NOT NULL DEFAULT 1, " % Table.COUNT +
                       "%s TIMESTAMP DEFAULT CURRENT_TIMESTAMP, " % Table.CREATED_AT +
                       "%s TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP)" % Table.LAST_VIEWED_AT
                       )
        cursor.close()

    def drop_table(self):
        cursor = self.database.cursor()
        cursor.execute("DROP TABLE %s" % Table.NAME)
        cursor.close()

    def increase_count(self, filename: str):
        cursor = self.database.cursor()
        query = "INSERT INTO %s (%s) VALUES ('%s')" % (Table.NAME, Table.FILENAME, filename) + \
                " ON DUPLICATE KEY UPDATE %s = %s + 1" % (Table.COUNT, Table.COUNT)
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def unregister_filename(self, filename: str):
        cursor = self.database.cursor()
        query = "DELETE FROM %s WHERE %s='%s'" % (Table.NAME, Table.FILENAME, filename)
        cursor.execute(query)
        self.database.commit()
        cursor.close()

    def fetch_all(self) -> ():
        cursor = self.database.cursor()
        query = "SELECT * FROM %s" % Table.NAME
        cursor.execute(query)
        items = cursor.fetchall()
        cursor.close()
        return items

    def fetch_names(self):
        cursor = self.database.cursor()
        query = "SELECT %s FROM %s" % (Table.FILENAME, Table.NAME)
        cursor.execute(query)
        tuples = cursor.fetchall()
        cursor.close()
        names = []
        for i, name in enumerate(tuples):
            names.append(tuples[i][0])
        return names

    def fetch_sizes(self, filename: str):
        cursor = self.database.cursor()
        query = "SELECT %s FROM %s " % (Table.SIZE, Table.NAME) + \
            "WHERE %s='%s'" % (Table.FILENAME, filename)
        cursor.execute(query)
        tuples = cursor.fetchall()
        cursor.close()
        sizes = []
        for i, size in enumerate(tuples):
            sizes.append(tuples[i][0])
        return sizes

    def close_connection(self):
        self.database.close()
