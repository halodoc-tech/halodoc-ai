# -*- coding: utf-8 -*-
"""
A reusable database connector module for MySQL and PostgreSQL.

This module provides a unified interface to connect to and interact with
MySQL and PostgreSQL databases. It handles connection management,
query execution, and fetching results.

Required libraries:
- for MySQL: pip install mysql-connector-python
- for PostgreSQL: pip install psycopg2-binary
"""

import mysql.connector
from contextlib import contextmanager


class DbConnectionError(Exception):
    """Custom exception for database connection errors."""
    pass

@contextmanager
def mysql_connection(host, user, password, database, port=3306):
    """
    Context manager for a MySQL database connection.

    Args:
        host (str): The database host.
        user (str): The username for the database.
        password (str): The password for the database.
        database (str): The name of the database.

    Yields:
        A tuple containing the connection and cursor objects.
    """
    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=host,
            user=user,
            password=password,
            database=database,
            port=port
        )
        cursor = conn.cursor(dictionary=True) # dictionary=True returns rows as dicts
        print("MySQL connection successful.")
        yield conn, cursor
    except mysql.connector.Error as e:
        print(f"Error connecting to MySQL database: {e}")
        raise DbConnectionError(e) from e
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()
            print("MySQL connection closed.")

def execute_query(cursor, query, params=None):
    """
    Executes a given SQL query.
    """
    cursor.execute(query, params or ())
    return cursor

def fetch_all(cursor):
    """
    Fetches all rows from a cursor.
    """
    rows = cursor.fetchall()
    return [dict(row) for row in rows]

def fetch_one(cursor):
    """
    Fetches one row from a cursor.
    """
    row = cursor.fetchone()
    return dict(row) if row else None
