import asyncio
import logging
import os
import random
import re
import smtplib
import sqlite3
import time
import psycopg2
from datetime import datetime, timedelta, timezone
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
import pytz
import requests
import toml
from dateutil.relativedelta import relativedelta
from nio import AsyncClient, MatrixRoom
from disposable_email_domains import blocklist

import bot_strings
import pm_functions as pmf
from config import settings
from lemmy_manager import get_lemmy_instance, restart_bot
from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType, FeatureType


# get lemmy instance
lemmy = get_lemmy_instance()

# logging stuff for healthcheck
LOG_FILE_PATH = 'resources/zippy.log'

log_level = getattr(logging, settings.DEBUG_LEVEL.upper(), logging.INFO)

logger = logging.getLogger()
logger.setLevel(log_level)

# write to healthcheck file
file_handler = logging.FileHandler(LOG_FILE_PATH)
file_handler.setLevel(log_level)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))

# write to stderr
stream_handler = logging.StreamHandler()
stream_handler.setLevel(log_level)
stream_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))

# Add the handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stream_handler)

logging.info("Log level set to %s", settings.DEBUG_LEVEL)

def create_table(conn, table_name, table_definition):
    curs = conn.cursor()
    curs.execute(
        f'''CREATE TABLE IF NOT EXISTS {table_name} {table_definition}''')
    conn.commit()
    logging.debug("Checked/created %s table", table_name)


def check_dbs():
    """
    Check the status of the configured databases and ensure they are accessible.

    This function is used to validate database connections and configurations.
    """
    try:
        with sqlite3.connect('resources/vote.db') as conn:
            # Create or check votes table
            create_table(
                conn,
                'votes',
                '(vote_id INT, username TEXT, vote_result TEXT, account_age TEXT)')

            # Create or check polls table
            create_table(
                conn,
                'polls',
                '(poll_id INTEGER PRIMARY KEY AUTOINCREMENT, poll_name TEXT, username TEXT, open TEXT)')

        with sqlite3.connect('resources/users.db') as conn:
            # Create or check users table
            create_table(
                conn,
                'users',
                '(local_user_id INT, public_user_id INT, username TEXT, has_posted INT, has_had_pm INT, email TEXT, subscribed INT)')

            # Create or check communities table
            create_table(
                conn,
                'communities',
                '(community_id INT, community_name TEXT)')

        with sqlite3.connect('resources/games.db') as conn:
            # create or check game deals table
            create_table(conn, 'deals', '(deal_name TEXT, deal_date TEXT)')

        with sqlite3.connect('resources/welcome/welcome.db') as conn:
            # create or check welcome messages table
            create_table(
                conn,
                'messages',
                '(community TEXT UNIQUE, message TEXT)')

        with sqlite3.connect('resources/mod_actions.db') as conn:
            # create or check new posts table
            create_table(
                conn,
                'new_posts',
                '(post_id INT, poster_id INT, mod_action STR)')

            # create or check new comments table
            create_table(
                conn,
                'new_comments',
                '(comment_id INT, comment_poster INT, mod_action STR)')

            # create or check community words table
            create_table(
                conn,
                'community_words',
                '(community TEXT UNIQUE, words TEXT, action TEXT)')

            # create or check user warnings table
            create_table(
                conn,
                'warnings',
                '(user_id INT, warning_reason TEXT, admin TEXT)')
            
            # create or check pm spam table
            create_table(
                conn,
                'pm_spam',
                '(id INTEGER PRIMARY KEY AUTOINCREMENT, phrase TEXT NOT NULL)')

            # create or check rss tables
        with sqlite3.connect('resources/rss.db') as conn:
            create_table(conn, 'feeds', '''
                (feed_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_url TEXT NOT NULL UNIQUE,
                url_contains_filter TEXT,
                title_contains_filter TEXT,
                url_excludes_filter TEXT,
                title_excludes_filter TEXT,
                community TEXT,
                tag TEXT,
                body BOOL,
                last_updated TIMESTAMP)
            ''')

            create_table(conn, 'posts', '''
                (post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                feed_id INTEGER,
                post_url TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                posted BOOLEAN DEFAULT 0,
                post_date TIMESTAMP,
                FOREIGN KEY(feed_id) REFERENCES feeds(feed_id))
            ''')

            # create or check reports tables
        with sqlite3.connect('resources/reports.db') as conn:
            create_table(
                conn,
                'post_reports',
                '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, post_id INT)')

            create_table(
                conn,
                'comment_reports',
                '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, comment_id INT)')

            # create_table(conn, 'message_reports', '(report_id INT, reporter_id INT, reporter_name TEXT, report_reason TEXT, message_id INT)')

        with sqlite3.connect('resources/autopost.db') as conn:
            create_table(
                conn,
                'com_posts',
                '(pin_id INTEGER PRIMARY KEY AUTOINCREMENT, community_id INT, mod_id INT, post_title TEXT, post_url TEXT, post_body TEXT, scheduled_post TIME, frequency TEXT, previous_post INT)')

        with sqlite3.connect('resources/giveaway.db') as conn:
            create_table(
                conn,
                'giveaways',
                '(giveaway_id INTEGER PRIMARY KEY, thread_id TEXT, status TEXT DEFAULT "active")')

            create_table(
                conn,
                'entrants',
                '(ticket_number INTEGER PRIMARY KEY AUTOINCREMENT, giveaway_id INTEGER, username TEXT, entry_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (giveaway_id) REFERENCES giveaways (giveaway_id), UNIQUE (giveaway_id, username))')
            
        with sqlite3.connect('resources/tags.db') as conn:
            create_table(
                conn,
                'enforcement_rules',
                """(id INTEGER PRIMARY KEY AUTOINCREMENT, enforcement_id INTEGER, community TEXT NOT NULL, tags TEXT NOT NULL, action_order INTEGER NOT NULL, action TEXT NOT NULL, duration INTEGER, message TEXT, FOREIGN KEY(enforcement_id) REFERENCES enforcement_sets(id))""")

            create_table(
                conn,
                'enforcement_sets',
                """(id INTEGER PRIMARY KEY AUTOINCREMENT, community TEXT, tags TEXT)""")
            
            create_table(
                conn,
                'enforcement_log',
                """(id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, community TEXT NOT NULL, rule_id INTEGER NOT NULL, current_step INTEGER NOT NULL, next_action_due TIMESTAMP NOT NULL, FOREIGN KEY (rule_id) REFERENCES enforcement_rules(id))""")

        
        with sqlite3.connect('resources/welcome/bus.db') as conn:
            create_table(
                conn,
                'pm_scan_messages',
                """(id INTEGER PRIMARY KEY, bot_sender TEXT, pm_id INT, pm_sender INT, pm_content TEXT)""")
            

        logging.debug("All tables checked.")

    except sqlite3.Error as e:
        logging.error("Database error: %s", e)
    except Exception as e:
        logging.error("Exception in _query: %s", e)



def connect_to_vote_db():
    return sqlite3.connect('resources/vote.db')


def connect_to_rss_db():
    return sqlite3.connect('resources/rss.db')


def connect_to_users_db():
    return sqlite3.connect('resources/users.db')


def connect_to_welcome_db():
    return sqlite3.connect('resources/welcome/welcome.db')


def connect_to_reports_db():
    return sqlite3.connect('resources/reports.db')


def connect_to_autopost_db():
    return sqlite3.connect('resources/autopost.db')


def connect_to_mod_db():
    return sqlite3.connect('resources/mod_actions.db')


def connect_to_giveaway_db():
    return sqlite3.connect('resources/giveaway.db')


def connect_to_games_db():
    return sqlite3.connect('resources/games.db')

def connect_to_tags_db():
    return sqlite3.connect('resources/tags.db')

def connect_to_message_bus_db():
    return sqlite3.connect('resources/welcome/bus.db')

def execute_sql_query(connection, query, params=()):
    with connection:
        curs = connection.cursor()
        curs.execute(query, params)
        return curs.fetchone()


def check_version():
 # confirm to admin chat zippybot is up and running
    last_version_file = 'resources/last_ver'
    last_version = None
    current_time = datetime.now()
    time_string = current_time.strftime("%H:%M:%S")

    config = toml.load('.bumpversion.toml')
    current_version = config["tool"]["bumpversion"]["current_version"]

    if os.path.exists(last_version_file):
        with open(last_version_file, "r") as f:
            last_version = f.read().strip()

    if last_version != current_version:
        logging.info("Version updated: %s -> %s", last_version, current_version)
        with open(last_version_file, "w") as f:
            f.write(current_version)
        logging.debug("All tables checked.")

        if settings.STARTUP_WARNING and settings.MATRIX_FLAG:
            matrix_body = f"ZippyBot has been updated and has restarted at {time_string}. Version updated: {last_version} -> {current_version}"
            asyncio.run(send_matrix_message(matrix_body))
            return

    if settings.STARTUP_WARNING and settings.MATRIX_FLAG:

        matrix_body = f"ZippyBot has been rebooted at {time_string}. If you weren't expecting this, Zippy has recovered from a crash."
        asyncio.run(send_matrix_message(matrix_body))

    logging.info("Bot Version %s", current_version)


def add_vote_to_db(pm_username, vote_id, vote_response, pm_account_age):
    try:
        with connect_to_vote_db() as conn:
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id, poll_name FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (vote_id,))

            if check_valid is None:
                logging.debug(
                    "Submitted vote_id did not match a valid poll_id")
                return "notvalid"

            # check poll is still open
            closed_query = '''SELECT poll_id, open FROM polls where poll_id=?'''
            check_open = execute_sql_query(conn, closed_query, (vote_id,))
            if check_open[1] == "0":
                return "closed"

            poll_name = check_valid[1]
            # Check if vote response is already recorded for this user/vote id
            vote_query = '''SELECT vote_id, username FROM votes WHERE vote_id=? AND username=?'''
            row = execute_sql_query(conn, vote_query, (vote_id, pm_username))

            if row:
                logging.debug("Matching vote found")
                return "duplicate"

            # If no duplicate votes, add new vote
            sqlite_insert_query = """INSERT INTO votes (vote_id, username, vote_result, account_age) VALUES (?, ?, ?, ?);"""
            data_tuple = (vote_id, pm_username, vote_response, pm_account_age)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added vote to database")
            return poll_name
    except Exception as e:
        logging.error(f"An error occurred: %s", e)
        return "error"


def create_poll(poll_name, pm_username):
    try:
        with connect_to_vote_db() as conn:
            isopen = True
            data_tuple = (poll_name, pm_username, isopen)
            sqlite_insert_query = """INSERT INTO polls (poll_name, username, open) VALUES (?, ?, ?);"""
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            # Get the ID of the poll just created
            poll_id_query = "SELECT last_insert_rowid()"
            poll_id = execute_sql_query(conn, poll_id_query)[0]

            logging.debug(
                f"Added poll to database with ID number {poll_id}")
            return poll_id
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def close_poll(poll_id):
    try:
        with connect_to_vote_db() as conn:
            set_open = "0"
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (poll_id,))

            if check_valid is None:
                logging.debug(
                    "Submitted vote_id did not match a valid poll_id")
                return "notvalid"

            sqlite_update_query = """UPDATE polls SET open = ? WHERE poll_id = ?;"""
            execute_sql_query(conn, sqlite_update_query, (set_open, poll_id))
            return "closed"
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def count_votes(poll_id):
    try:
        with connect_to_vote_db() as conn:
            yes_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'yes' AND vote_id = ?;"
            no_query = "SELECT COUNT(*) FROM votes WHERE vote_result = 'no' AND vote_id = ?;"
            yes_count = execute_sql_query(conn, yes_query, (poll_id,))[0]
            no_count = execute_sql_query(conn, no_query, (poll_id,))[0]
            return yes_count, no_count

    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def add_autopost_to_db(post_data):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = """
            INSERT INTO com_posts (community_id, mod_id, post_title, post_url, post_body, frequency, scheduled_post)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            values = (
                post_data['community'],
                post_data['mod_id'],
                post_data['title'],
                post_data['url'],
                post_data['body'],
                post_data['frequency'],
                post_data['scheduled_post']
            )
            cursor.execute(query, values)
            conn.commit()

            # Get the ID of the autopost just created
            autopost_id_query = "SELECT last_insert_rowid()"
            autopost_id = execute_sql_query(conn, autopost_id_query)[0]
            return autopost_id
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def delete_rss(feed_id, pm_sender):
    try:
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM feeds WHERE feed_id = ?", (feed_id,))
        feed = cursor.fetchone()
        if feed is None:
            return "no_exist"

        community = feed[6]

        output = lemmy.community.get(community)

        # check if user is moderator of community
        is_moderator = False

        for moderator_info in output['moderators']:
            if moderator_info['moderator']['id'] == pm_sender:
                is_moderator = True
                break

        if not is_moderator:
            return "not_mod"

        cursor.execute("DELETE FROM posts WHERE feed_id = ?", (feed_id,))
        cursor.execute("DELETE FROM feeds WHERE feed_id = ?", (feed_id,))
        conn.commit()
        logging.info("Feed and related posts deleted successfully.")
        return "deleted"

    except sqlite3.IntegrityError as e:
        logging.debug("Integrity error: %s", e)
    except sqlite3.Error as e:
        logging.debug("Database error: %s", e)
    except Exception as e:
        logging.debug("Unexpected error: %s", e)


def delete_welcome(com_name, pm_sender):
    try:
        with connect_to_welcome_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM messages WHERE community = ?", (com_name,))
            row = cursor.fetchone()
            if row is None:
                return "no_exist"

        output = lemmy.community.get(name=com_name)
        is_moderator = False
        for moderator_info in output['moderators']:
            if moderator_info['moderator']['id'] == pm_sender:
                is_moderator = True
                break

        if not is_moderator:
            return "not_mod"

        cursor.execute("DELETE FROM messages WHERE community = ?", (com_name,))
        conn.commit()
        return "deleted"

    except sqlite3.IntegrityError as e:
        logging.debug("Integrity error: %s", e)
    except sqlite3.Error as e:
        logging.debug("Database error: %s", e)
    except Exception as e:
        logging.debug("Unexpected error: %s", e)


def delete_autopost(pin_id, pm_sender, del_post):
    try:
        with connect_to_autopost_db() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM com_posts WHERE pin_id = ?"
            cursor.execute(query, (pin_id,))
            full_row = cursor.fetchone()

            community_name = full_row[1]
            mod_id = full_row[2]
            prev_post = full_row[8]

            # check it has not already been deleted
            if community_name is None:
                return "no id"

            # check if delete request came from original author
            if mod_id == pm_sender:
                query = "DELETE FROM com_posts WHERE pin_id = ?"
                cursor.execute(query, (pin_id,))
                conn.commit()
                if prev_post is not None:
                    if del_post:
                        lemmy.post.delete(prev_post, True)
                return "deleted"

            # not a match, check if sender is a mod of the community
            output = lemmy.community.get(name=community_name)

            is_moderator = False

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == pm_sender:
                    is_moderator = True
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (pin_id,))
                    conn.commit()
                    if prev_post is not None:
                        if del_post:
                            lemmy.post.delete(prev_post, True)
                    return "deleted"

            if not is_moderator:
                return "not mod"

    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def clear_notifications():
    try:
        notif = lemmy.comment.get_replies(True, 1)
        all_notifs = notif['replies']
    except requests.exceptions.ConnectionError:
        logging.info(
            "Error with connection, skipping checking clearing notifications...")
        return
    except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
        logging.info("Error with Timeout - pausing bot for 30 seconds...")
        time.sleep(30)
        return
    except requests.exceptions.HTTPError:
        logging.info("Error with HTTP connection, restarting bot...")
        restart_bot()    
        return


    for notif in all_notifs:
        reply_id = notif['comment_reply']['id']
        lemmy.comment.mark_as_read(reply_id, True)

def check_pms():
    try:
        pm = lemmy.private_message.list(True, 1)
        
        if pm is None:
            logging.info("No data received from private message API. Skipping...")
            return

        private_messages = pm.get('private_messages', [])

    except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
        logging.info("Error with Timeout - pausing bot for 30 seconds...")
        time.sleep(30)
        return

    except requests.exceptions.ConnectionError:
        logging.info("Error with connection, skipping checking private messages...")
        return

    except requests.exceptions.HTTPError:
        logging.info("Error with HTTP connection, restarting bot...")
        restart_bot()    
        return

    for pm_data in private_messages:
        pm_sender = pm_data['private_message']['creator_id']
        pm_username = pm_data['creator']['name']
        pm_context = pm_data['private_message']['content']
        pm_id = pm_data['private_message']['id']
        pm_account_age = pm_data['creator']['published']

        output = lemmy.user.get(pm_sender)
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['is_admin']

        # first make sure the pm isn't coming from zippy otherwise it'll put
        # zippy in a loop.
        if pm_sender == settings.BOT_ID:
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        # IMPORTANT keep this here - only put reply code above that you want
        # ANYONE ON LEMMY/FEDIVERSE TO BE ABLE TO ACCESS outside of your
        # instance when they message your bot.
        if user_local != settings.LOCAL:
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username} \n\n {bot_strings.LOCAL_ONLY_WARNING}\n \n {bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#help":
            pmf.pm_help(user_admin, pm_username, pm_id, pm_sender)
            continue
        
        if pm_context == "#autoposthelp":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.AUTOPOST_HELP}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == '#rsshelp':
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.RSS_HELP}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#rules":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.INS_RULES}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#credits":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.CREDITS}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#feedback":
            lemmy.private_message.create(f"{bot_strings.GREETING} {pm_username}\n\n{bot_strings.FEEDBACK_MESSAGE}\n\n{bot_strings.PM_SIGNOFF}", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context in ["#unsubscribe", "#subscribe"]:
            status = "unsub" if pm_context == "#unsubscribe" else "sub"
            pmf.pm_sub(pm_sender, status, pm_username, pm_id, broadcast_status)
            continue


        if pm_context.split(" -")[0] == "#takeover":
            pmf.pm_takeover(user_admin, pm_context, pm_id, pm_username, pm_sender)
            continue

        if pm_context.split(" ")[0] == "#vote":
            pmf.pm_vote(pm_context, pm_username, pm_account_age, pm_id, pm_sender, add_vote_to_db)
            continue

        if pm_context.split(" @")[0] == "#poll":
            pmf.pm_poll(user_admin, pm_context, pm_username, pm_id, pm_sender, create_poll)
            continue
        
        if pm_context.split(" @")[0] == "#closepoll":
            pmf.pm_closepoll(user_admin, pm_context, pm_username, pm_id, pm_sender, close_poll)
            continue

        if pm_context.split(" @")[0] == "#countpoll":
            pmf.pm_countpoll(user_admin, pm_context, pm_username, pm_id, pm_sender, count_votes)
            continue

        if pm_context.split(" ")[0] == "#giveaway":
            pmf.pm_giveaway(user_admin, pm_id, pm_context, add_giveaway_thread)
            continue
        
        if pm_context.split(" ")[0] == "#closegiveaway":
            pmf.pm_closegiveaway(user_admin, close_giveaway_thread, pm_context, pm_id)
            continue
        
        if pm_context.split(" ")[0] == "#drawgiveaway":
            pmf.pm_drawgiveaway(user_admin, draw_giveaway_thread, pm_context, pm_username, pm_sender, pm_id)
            continue

        # broadcast messages
        if pm_context.split(" ")[0] == "#broadcast":
            pmf.pm_broadcast(user_admin, pm_context, pm_id, broadcast_message)
            continue

        if pm_context.split(" ")[0] == "#rssdelete":
            pmf.pm_rssdelete(pm_context, pm_sender, pm_username, pm_id, delete_rss)
            continue

        if pm_context.split(" ")[0] == "#welcomedelete":
            pmf.pm_welcomedelete(pm_context, pm_username, pm_sender, pm_id, delete_welcome)
            continue

        # mod action - add words to be scanned for community
        if pm_context.split(" ")[0] == "#comscan":
            pmf.pm_comscan(pm_context, pm_username, pm_sender, pm_id, add_community_word)
            continue

        # mod action - add welcome message to community
        if pm_context.split(" ")[0] == "#welcome":
            pmf.pm_welcome(pm_context, pm_username, pm_sender, pm_id, add_welcome_message)
            continue

        # mod/admin action - create rss feed in community
        if pm_context.split(" ")[0] == "#rss":
            pmf.pm_rss(pm_context, pm_username, pm_sender, pm_id, add_new_feed, connect_to_rss_db, fetch_latest_posts, insert_new_post)
            continue

        # mod action - pin a post
        if pm_context.split(" ")[0] == '#autopost':
            pmf.pm_autopost(pm_context, pm_username, pm_sender, pm_id, add_autopost_to_db, get_first_post_date)
            continue

        if pm_context.split(" ")[0] == "#autopostdelete":
            pmf.pm_autopostdelete(pm_context,delete_autopost,pm_username,pm_sender,pm_id)
            continue

        if pm_context == "#purgevotes":
            pmf.pm_purgevotes(user_admin, pm_id, check_dbs)
            continue

        if pm_context == "#purgeadminactions":
            pmf.pm_purgeadminactions(user_admin, pm_id, check_dbs)
            continue

        if pm_context == "#purgerss":
            pmf.pm_purgerss(user_admin, pm_id, check_dbs)

        if pm_context.split(" ")[0] == "#reject":
            pmf.pm_reject(pm_context, pm_sender, pm_username, pm_id, reject_user)
            continue

        if pm_context.split(" ")[0] == "#ban":
            pmf.pm_ban(user_admin, pm_sender, pm_context, pm_id, ban_email, send_matrix_message)
            continue

        if pm_context.split(" ")[0] == '#warn':
            pmf.pm_warn(user_admin, pm_context, pm_username, pm_id, pm_sender, ordinal, get_warning_count, send_matrix_message, log_warning)
            continue

        if pm_context.split(" ")[0] == '#lock':
            pmf.pm_lock(user_admin, pm_context, pm_username, pm_id, send_matrix_message)
            continue
        
        if pm_context.split(" ")[0] == "#tagenforcer":
            pmf.pm_tagenforcer(pm_username, pm_context, pm_sender, pm_id, store_enforcement)
            continue
        
        if pm_context.split(" ")[0] == "#hide":
            pmf.pm_hide(user_admin, pm_context, pm_sender, pm_id, pm_username, send_matrix_message)
            continue
        
        if pm_context.split(" ")[0] == "#spam_add":
            pmf.pm_spam_add(user_admin, pm_context, pm_sender, pm_id, pm_username, add_pm_spam_phrase)

        # keep this at the bottom
        pmf.pm_notunderstood(pm_username, pm_sender, pm_id)
        continue
 
def is_spam_email(email):

    suspicious_keywords = {"seo", "info", "sales", "media", "news", "marketing"}

    # Count the number of digits in the email
    num_count = sum(char.isdigit() for char in email)

    # Split the email address at '@' to extract the domain
    local_part, domain = email.split('@')

    # Logging the domain for debugging
    logging.info("Checking spam email with domain: %s", domain)

    contains_suspicious_keyword = any(
        keyword in local_part.lower() for keyword in suspicious_keywords)
    
    # Count the number of dots in the local part
    dot_count = local_part.count('.')

    # Check if the email is spam based on the number of digits or if the
    # domain is a known spam domain
    return num_count > 4 or dot_count > 1 or domain in blocklist or contains_suspicious_keyword



def get_new_users():
    try:
        output = lemmy.admin.list_applications()

        # Ensure output is not None before accessing it
        if not output:
            logging.error("Received None from API, skipping and backing off...")
            time.sleep(30)
            return
        
        if "error" in output and output["error"] == "rate_limit_error":
            logging.warning("Rate limit hit, sleeping for 60 seconds...")
            time.sleep(60)
            return

        new_apps = output.get('registration_applications', [])

    except requests.exceptions.ConnectionError:
        logging.info("Error with connection, skipping checking new applications...")
    except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
        logging.info("Error with Timeout - pausing bot for 30 seconds...")
        time.sleep(30)
    except requests.exceptions.HTTPError:
        logging.info("Error with HTTP connection, restarting bot...")
        restart_bot()

    for output in new_apps:
        local_user_id = output['registration_application']['local_user_id']
        username = output['creator']['name']
        email = output['creator_local_user'].get('email')
        public_user_id = output['creator_local_user']['person_id']
        
        if email is None:
            continue

        if update_registration_db(
                local_user_id,
                username,
                public_user_id,
                email) == "new_user":
            logging.debug("sending new user a pm")
            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                username +
                ". " +
                bot_strings.WELCOME_MESSAGE +
                bot_strings.PM_SIGNOFF,
                public_user_id)

            # Check if the email is from a known spam domain
            if is_spam_email(email):
                logging.info("User %s tried to register with a potential spam email: %s", username, email)

                matrix_body = f"New user {username} (https://{settings.INSTANCE}/u/{username}) with ID {public_user_id} has signed up with an email address that may be a temporary or spam email address: {email}"
                asyncio.run(send_matrix_message(matrix_body))

            if settings.EMAIL_FUNCTION:
                welcome_email(email)
                
            insert_block(public_user_id)

        continue


def update_registration_db(local_user_id, username, public_user_id, email):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            # search db for matching user id
            curs.execute(
                'SELECT local_user_id FROM users WHERE local_user_id=?', (local_user_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching ID found, ignoring")
                return "User ID already exists"

            # default user to subscribed list
            subscribed = 1

            logging.debug("User ID did not match an existing user ID, adding")
            sqlite_insert_query = "INSERT INTO users (local_user_id, public_user_id, username, email, subscribed) VALUES (?, ?, ?, ?, ?);"
            data_tuple = (
                local_user_id,
                public_user_id,
                username,
                email,
                subscribed)

            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new user to database")
            return "new_user"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"


def get_communities():
    try:
        communities = lemmy.community.list(
            limit=5, page=1, sort=SortType.New, type_=ListingType.Local)
        local_comm = communities

    except requests.exceptions.ConnectionError:
        logging.info(
            "Error with connection, skipping getting communities...")
        return
    except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
        logging.info("Error with Timeout - pausing bot for 30 seconds...")
        time.sleep(30)
        return
    except requests.exceptions.HTTPError:
        logging.info("Error with HTTP connection, restarting bot...")
        restart_bot()    
        return


    for communities in local_comm:
        community_id = communities['community']['id']
        community_name = communities['community']['name']

        find_mod = lemmy.community.get(community_id)

        if find_mod is None or find_mod.get('moderators') is None:
            logging.info("Unable to get moderator of community, skipping.")
            continue

        mods = find_mod['moderators']

        for find_mod in mods:
            mod_id = find_mod['moderator']['id']
            mod_name = find_mod['moderator']['name']

        if new_community_db(community_id, community_name) == "community":
            lemmy.private_message.create(
                bot_strings.GREETING +
                " " +
                mod_name +
                ". Congratulations on creating your community, [" +
                community_name +
                "](/c/" +
                community_name +
                "@" +
                settings.INSTANCE +
                "). \n " +
                bot_strings.MOD_ADVICE +
                bot_strings.PM_SIGNOFF,
                mod_id)


def add_giveaway_thread(thread_id):
    try:
        with connect_to_giveaway_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO giveaways (thread_id) VALUES (?)', (thread_id,))
            conn.commit()
            giveaway_id = cursor.lastrowid
            return giveaway_id
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"


def close_giveaway_thread(thread_id):
    with connect_to_giveaway_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE giveaways SET status = ? WHERE thread_id = ?',
            ('closed',
             thread_id))
        conn.commit()


def draw_giveaway_thread(thread_id, num_winners):
    with connect_to_giveaway_db() as conn:
        cursor = conn.cursor()

        cursor.execute(
            'SELECT giveaway_id FROM giveaways WHERE thread_id = ?', (thread_id,))
        result = cursor.fetchone()

        giveaway_id = result[0]
        cursor.execute('''
                SELECT username FROM entrants
                WHERE giveaway_id = ?
                ORDER BY RANDOM()
            ''', (giveaway_id,))
        entrants = cursor.fetchall()

        if len(entrants) < int(num_winners):
            return "min_winners"
        usernames = [entrant[0] for entrant in entrants]
        random.shuffle(usernames)
        winners = random.sample(usernames, int(num_winners))
        return winners


def check_giveaways(thread_id,comment_poster,comment_username):
    # check if post is in db
    with connect_to_giveaway_db() as conn:
        action_query = '''SELECT giveaway_id, status FROM giveaways WHERE thread_id=?'''
        thread_match = execute_sql_query(conn, action_query, (thread_id,))

        if thread_match:
            giveaway_id = thread_match[0]
            status = thread_match[1]

            if status == 'closed':
                return
            try:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO entrants (giveaway_id, username) VALUES (?, ?)',
                    (giveaway_id,
                     comment_username))
                conn.commit()
                ticket_number = cursor.lastrowid
                logging.info("User '%s' has entered giveaway '%s' with ticket number '%s'", comment_poster, giveaway_id, ticket_number)
                lemmy.private_message.create(f"{bot_strings.GREETING} {comment_username}. Your giveaway entry has been recorded! Your entry number is #{ticket_number} - Good luck!", comment_poster)
            except sqlite3.IntegrityError:
                logging.info("User '%s' has already entered giveaway '%s'", comment_poster, giveaway_id)


def new_community_db(community_id, community_name):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            # search db to see if community exists in DB already
            curs.execute(
                'SELECT community_id FROM communities WHERE community_id=?', (community_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching community ID found, ignoring")
                return "Community ID already exists"

            logging.debug(
                "community ID did not match an existing community ID, adding")
            sqlite_insert_query = "INSERT INTO communities (community_id, community_name) VALUES (?, ?);"
            data_tuple = (community_id, community_name)

            curs.execute(sqlite_insert_query, data_tuple)
            logging.debug("Added new community to database")
            return "community"
    except sqlite3.Error as error:
        logging.error("Failed to execute sqlite statement", error)
        return "Database error occurred"
    except Exception as error:
        logging.error("An error occurred", error)
        return "An unknown error occurred"





def welcome_email(email):
    message = MIMEMultipart()
    message['From'] = settings.SENDER_EMAIL
    message['To'] = email
    message['Subject'] = bot_strings.EMAIL_SUBJECT

    # use this for a simple text email, uncomment below:
    # body
    # body = bot_strings.EMAIL_SUBJECT + ".\n\n We've received your application and one of our Admins will manually verify your account shortly. \n\n Lemmy.zip prides itself on being a welcoming and inclusive Lemmy instance, and to help reduce spam we manually verify all accounts.\n\n Once your account is accepted, you will receive another email from us confirming this and then you'll be able to log in to your account using the details you set up. You won't be able to login until you've received this confirmation email.\n\n If you've not received an email confirming you have been accepted within a couple of hours, please email hello@lemmy.zip with your username, and we can look into the issue further. Please be patient with us!\n\n Thanks again for signing up to Lemmy.zip, we're excited to welcome you to the Fediverse :)\n\n PS - Once you've logged in, look out for a message from ZippyBot with a guide on how to get started!"
    # message.attach(MIMEText(body, 'plain'))

    # use this for sending a HTML email i.e. with pictures and colours.
    # html email - resources to be saved in the "resources" folder
    with open('resources/index.html', 'r', encoding='utf-8') as html_file:
        html_content = html_file.read()
    # Attach the HTML content to the email
    message.attach(MIMEText(html_content, 'html'))

    # Attach the image as an inline attachment
    with open('resources/images/image-1.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        # use content ids and change to img tag in html to match
        image.add_header('Content-ID', '<image-1>')
        message.attach(image)

    with open('resources/images/image-2.png', 'rb') as image_file:
        image = MIMEImage(image_file.read())
        image.add_header('Content-ID', '<image-2>')
        message.attach(image)

    # initialise SMTP server - keep from here for either email type.
    try:
        server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
        server.starttls()
        server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
        server.sendmail(settings.SENDER_EMAIL, email, message.as_string())
        logging.info("Welcome email sent successfully")
    except Exception as e:
        logging.error("Error: Unable to send email.", str(e))
    finally:
        server.quit()


def ban_email(person_id):
    with sqlite3.connect('resources/users.db') as conn:
        curs = conn.cursor()

        curs.execute(
            'SELECT email FROM users WHERE public_user_id = ?', (person_id,))
        id_match = curs.fetchone()

        # usr not in db
        if not id_match:
            return "notfound"

        email = id_match[0]

        message = MIMEMultipart()
        message['From'] = settings.SENDER_EMAIL
        message['To'] = email
        message['Subject'] = "Lemmy.zip - Account Ban"

        body = f"""
            <p>Hello, this is an automated message to let you know your Lemmy.zip account has received a ban.</p>
            <p>You can see the details and reason for this ban at this link:
            <a href="https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}">
            https://lemmy.zip/modlog?page=1&actionType=ModBan&userId={person_id}</a>.</p>

            <p>If you would like to dispute this ban, please send an email to <a href="mailto:hello@lemmy.zip">hello@lemmy.zip</a>.
            During the period your account is banned for, you won't be able to access your account including logging in, posting, or voting. You can see our Terms of Service and Code of Conduct at
            <a href="https://legal.lemmy.zip">legal.lemmy.zip</a>.</p>

            <p><i>Please note, you cannot reply directly to this email. Please send appeals to hello@lemmy.zip.</i></p>
        """
        message.attach(MIMEText(body, 'html'))

        # send
        try:
            with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
                server.sendmail(
                    settings.SENDER_EMAIL,
                    email,
                    message.as_string())
                logging.info("Ban notification email sent successfully.")
                return "sent"
        except Exception as e:
            logging.error("Error: Unable to send email. %s", e)
            return "error"


def steam_deals():
    # url of the RSS Feed
    rss_url = "http://www.reddit.com/r/steamdeals/new/.rss?sort=new"

    # parse feed
    feed = feedparser.parse(rss_url)

    # loop through 10 entries
    for entry in feed.entries[:10]:
        content_value = entry.content[0]['value']
        steam_url = re.search(
            r'https://store\.steampowered\.com/app/\d+/\w+/',
            str(content_value))

        deal_published = entry.published
        deal_title = entry.title

        if steam_url:
            steam_url = steam_url.group()
        else:
            logging.info(
                "No store.steampowered.com URL found in the steam deals entry.")
            add_deal_to_db(deal_title, deal_published)
            continue

        if add_deal_to_db(deal_title, deal_published) == "added":
            community_id = lemmy.discover_community("gamedeals")
            lemmy.post.create(
                community_id,
                name="Steam Deal: " +
                deal_title,
                url=steam_url)


def RSS_feed():
    try:
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag
                FROM feeds
            """)
            feeds = cursor.fetchall()

        for feed in feeds:
            feed_id, feed_url, url_contains_filter, url_excludes_filter, title_contains_filter, title_excludes_filter, community, tag = feed
            posts = fetch_latest_posts(
                feed_url,
                url_contains_filter,
                url_excludes_filter,
                title_contains_filter,
                title_excludes_filter)

            if posts == "URL access error":
                logging.error("Skipping RSS Feed due to URL access error.")
                continue

            if not isinstance(posts, list):
                logging.error("Failed to fetch posts for feed URL %s. Error: %s", feed_url, posts)
                continue

            for post in posts:
                if insert_new_post(feed_id, post):
                    if tag:
                        post_title = f"[{tag}] " + post['title']
                    else:
                        post_title = post['title']
                    # actually post to lemmy here
                    logging.debug("Creating an RSS post.")
                    lemmy.post.create(
                        community_id=int(community),
                        name=post_title,
                        url=post['post_url'])
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def fetch_rss_feeds():
    try:
        logging.debug("Connecting to RSS DB to fetch RSS feeds")
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT feed_id, feed_url FROM feeds")
            feeds = cursor.fetchall()
        return feeds
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def fetch_latest_posts(
        feed_url,
        url_contains_filter=None,
        url_excludes_filter=None,
        title_contains_filter=None,
        title_excludes_filter=None):
    try:
        logging.debug("Fetching latest RSS posts from %s", feed_url)
        # Stream=True to only fetch headers
        response = requests.get(feed_url, stream=True, timeout=10)
        if response.status_code == 404:
            logging.error("URL not found (404): %s", feed_url)
            return "URL access error"

        if response.status_code == 403:
            logging.error("Access forbidden (403) to URL: %s", feed_url)
            return "URL access error"

        if response.status_code != 200:
            logging.error(
                "Failed to access URL %s. HTTP status code: %s", feed_url, response.status_code
            )
            return "URL access error"

        feed = feedparser.parse(feed_url)

        filtered_posts = []
        for entry in feed.entries[:3]:
            post_url = entry.link
            post_content = entry.title + ' ' + \
                entry.summary if hasattr(entry, 'summary') else entry.title

            # URL filter
            if url_contains_filter and not any(
                    filter_word in post_url for filter_word in url_contains_filter.split(',')):
                continue
            if url_excludes_filter and any(
                    filter_word in post_url for filter_word in url_excludes_filter.split(',')):
                continue

            # title filter
            if title_contains_filter and not any(
                    word in post_content for word in title_contains_filter.split(',')):
                continue
            if title_excludes_filter and any(
                    word in post_content for word in title_excludes_filter.split(',')):
                continue

            filtered_posts.append({
                'post_url': post_url,
                'title': entry.title,
                'description': entry.summary if hasattr(entry, 'summary') else '',
                'post_date': entry.published if hasattr(entry, 'published') else ''
            })
        return filtered_posts
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def insert_new_post(feed_id, post):
    try:
        logging.debug("Inserting new post to RSS DB")
        with connect_to_rss_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT post_id FROM posts WHERE post_url = ?", (post['post_url'],))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO posts (feed_id, post_url, title, description, posted, post_date) VALUES (?, ?, ?, ?, ?, ?)",
                    (feed_id,
                     post['post_url'],
                     post['title'],
                     post['description'],
                     0,
                     post['post_date']))
                conn.commit()
                return True
        return False
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def add_new_feed(
        feed_url,
        url_contains_filter,
        url_excludes_filter,
        title_contains_filter,
        title_excludes_filter,
        community,
        tag):
    conn = connect_to_rss_db()
    cursor = conn.cursor()

    cursor.execute(
        """SELECT feed_id FROM feeds WHERE feed_url = ? AND community = ?""",
        (feed_url,
         community))

    if cursor.fetchone():
        conn.close()
        return "exists"

    insert_query = """
    INSERT INTO feeds (feed_url, url_contains_filter, title_contains_filter, url_excludes_filter, title_excludes_filter, community, tag, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    values = (
        feed_url,
        url_contains_filter,
        title_contains_filter,
        url_excludes_filter,
        title_excludes_filter,
        community,
        tag,
        datetime.now())

    try:
        cursor.execute(insert_query, values)
        conn.commit()
        feed_id = cursor.lastrowid
        return feed_id
    except sqlite3.IntegrityError as e:
        logging.debug("An error occurred: %s", e)
        return None
    finally:
        conn.close()


def add_welcome_message(community, message):
    conn = connect_to_welcome_db()
    cursor = conn.cursor()

    insert_query = """
    INSERT OR REPLACE INTO messages (community, message)
    VALUES (?, ?)
    """

    values = (community, message)

    try:
        cursor.execute(insert_query, values)
        conn.commit()
        return "added"
    except sqlite3.IntegrityError as e:
        logging.debug("An error occurred: %s", e)
        return None
    finally:
        conn.close()


def add_community_word(community, words, action):
    conn = connect_to_mod_db()
    cursor = conn.cursor()

    if isinstance(words, str):
        new_words_set = set(words.split(','))
    elif isinstance(words, list):
        new_words_set = set(words)

    # fetch current list of words
    cursor.execute(
        "SELECT words FROM community_words WHERE community = ?", (community,))
    result = cursor.fetchone()
    if result:
        # Assuming words are stored as a comma-separated string
        current_words = result[0].split(',')
    else:
        current_words = []

    updated_words_set = set(current_words).union(new_words_set)

    updated_words = ','.join(updated_words_set)

    if result:
        # Update the existing entry
        cursor.execute(
            "UPDATE community_words SET words = ? WHERE community = ? AND action = ?",
            (updated_words,
             community,
             action))
    else:
        # Insert a new entry if none existed
        cursor.execute(
            "INSERT INTO community_words (community, words, action) VALUES (?, ?, ?)",
            (community,
             updated_words,
             action))

    conn.commit()
    conn.close()

    return "added"


def add_deal_to_db(deal_title, deal_published):
    try:
        with connect_to_games_db() as conn:
            # Check if bundble already is in db
            deal_query = '''SELECT deal_name, deal_date FROM deals WHERE deal_name=? AND deal_date=?'''
            deal_match = execute_sql_query(
                conn, deal_query, (deal_title, deal_published,))

            if deal_match:
                return "duplicate"

            logging.debug("New deal to be added to DB")

            sqlite_insert_query = """INSERT INTO deals (deal_name, deal_date) VALUES (?,?);"""
            data_tuple = (deal_title, deal_published,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added deal to database")
            return "added"
    except Exception as e:
        logging.error("An error occurred: %s", e)
        return "error"


def check_comments():
    recent_comments = lemmy.comment.list(
        limit=10, sort=SortType.New, type_=ListingType.Local)
    for comment in recent_comments:
        comment_id = comment['comment']['id']
        comment_text = comment['comment']['content']
        comment_poster = comment['creator']['id']

        # check if it has already been scanned
        if check_comment_db(comment_id) == "duplicate":
            continue

        # check if its a comment by a mod to delete a post
        if comment_text == "#delete":
            community = comment['community']['id']
            post = comment['post']['id']
            poster = comment['post']['creator_id']

            output = lemmy.community.get(id=community)

            for moderator_info in output['moderators']:
                if moderator_info['moderator']['id'] == comment_poster:
                    if poster == settings.BOT_ID:
                        lemmy.post.delete(post_id=post, deleted=True)

        community_name = comment['community']['name']

        # check if a giveaway post
        if settings.GIVEAWAY_ENABLED:

            comment_username = comment['creator']['name']
            creator_local = comment['creator']['local']
            thread_id = comment['post']['id']
            account_age = comment['creator']['published']

            if creator_local:
                account_age = datetime.strptime(
                    account_age, '%Y-%m-%dT%H:%M:%S.%fZ')
                # this is temporary and fixed, needs putting into the giveaways
                # table and adding as a variable to the PM command, so it can
                # be used as part of the wider mod toolset.
                set_date = datetime(2024, 6, 5)
                difference = set_date - account_age

                if difference > timedelta(days=3):
                    check_giveaways(
                        thread_id,
                        comment_poster,
                        comment_username)

        # Initialize match flags for each post
        match_found_text = False

        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT words FROM community_words WHERE community = ?", (community_name,))
            result = cursor.fetchone()
            if result:
                db_words_set = set(result[0].split(','))

                text_words_set = set(comment_text.lower().split())

                match_found_text = bool(db_words_set & text_words_set)

        if match_found_text:
            lemmy.comment.report(
                comment_id,
                reason="Word in comment appears on community banned list - Automated report by " +
                bot_strings.BOT_NAME)
            mod_action = "Comment Flagged"
            logging.info("Word matching regex found in content, reported.")

        else:
            mod_action = "None"

        add_comment_to_db(comment_id, comment_poster, mod_action)

        # admin matrix report
        regex_pattern = re.compile(settings.SLUR_REGEX)
        match_found = False

        if re.search(regex_pattern, comment_text.lower()):
            match_found = True

        if match_found:
            matrix_body = "Word(s) matching banned list appearing in comment https://" + \
                settings.INSTANCE + "/comment/" + str(comment_id) + ". - Please review urgently."
            asyncio.run(send_matrix_message(matrix_body))
            break


def check_comment_db(comment_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT comment_id FROM new_comments WHERE comment_id=?'''
            comment_match = execute_sql_query(
                conn, action_query, (comment_id,))

            if comment_match:
                return "duplicate"

    except Exception as e:
        logging.error("An error occurred: %s", e)
    return "error"


def add_comment_to_db(comment_id, comment_poster, mod_action):
    try:
        logging.debug("Adding new comment to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_comments (comment_id, comment_poster, mod_action) VALUES (?,?,?);"""
            data_tuple = (comment_id, comment_poster, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added comment to db")
            return "added"

    except Exception as e:
        logging.error("An error occurred: %s", e)
    return "error"


def check_posts():
    recent_posts = lemmy.post.list(
        limit=10,
        sort=SortType.New,
        type_=ListingType.Local)
    for post in recent_posts:
        post_id = post['post']['id']
        post_title = post['post']['name']

        # check if post has already been scanned
        if check_post_db(post_id) == "duplicate":
            continue

        # Check if 'body' exists in the 'post' dictionary
        if 'body' in post['post']:
            post_text = post['post']['body']
        else:
            post_text = "No body found"

        poster_id = post['creator']['id']
        poster_name = post['creator']['name']
        community_name = post['community']['name']

        # Initialize match flags for each post
        match_found_text = False
        match_found_title = False

        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT words FROM community_words WHERE community = ?", (community_name,))
            result = cursor.fetchone()
            if result:
                db_words_set = set(result[0].split(','))

                text_words_set = set(post_text.lower().split())
                title_words_set = set(post_title.lower().split())

                # Check for word matches in text and title
                match_found_text = bool(db_words_set & text_words_set)
                match_found_title = bool(db_words_set & title_words_set)

        if match_found_text or match_found_title:
            lemmy.post.report(
                post_id,
                reason="Word in post by user " +
                poster_name +
                " appears on community slur list - Automated report by " +
                bot_strings.BOT_NAME)
            mod_action = "Post Flagged"
            logging.info(
                "Word matching community ban list found in post by %s, reported.",
                poster_name
            )

        else:
            mod_action = "None"

        add_post_to_db(post_id, poster_id, mod_action)

        # admin matrix report
        regex_pattern = re.compile(settings.SLUR_REGEX)
        match_found = False

        if re.search(regex_pattern, post_text.lower()):
            match_found = True
        if re.search(regex_pattern, post_title.lower()):
            match_found = True

        if match_found:
            matrix_body = "Word(s) matching banned list appearing in post https://" + \
                settings.INSTANCE + "/post/" + str(post_id) + ". - Please review urgently."
            asyncio.run(send_matrix_message(matrix_body))
            break
        
        # Check if the post is meant to have a tag and doesn't have one
        with connect_to_tags_db() as conn:
            cursor = conn.cursor()
            # Check if the community has enforcement rules
            cursor.execute('SELECT DISTINCT tags FROM enforcement_rules WHERE community = ?', (community_name,))
            rows = cursor.fetchall()

            if not rows:
                continue
            
            # Get all required tags for this community
            required_tags = set()
            for row in rows:
                required_tags.update(row[0].split(","))  # Convert stored comma-separated tags into a set
            
            # Check if any of the required tags are in the post title
            if any(tag.lower() in post_title.lower() for tag in required_tags):
                return  # Post complies, no action needed
            
            # If the post does not contain the required tags, log it for enforcement
            log_tag_action(community_name, post_id)
            
def log_tag_action(community, post_id):
    with connect_to_tags_db() as conn:
        cursor = conn.cursor()

        # Get the first enforcement action for this community
        cursor.execute('''
            SELECT enforcement_id, action_order, action, duration, message 
            FROM enforcement_rules 
            WHERE community = ?
            ORDER BY action_order ASC
            LIMIT 1
        ''', (community,))
        first_action = cursor.fetchone()

        if not first_action:
            return  # No actions defined, nothing to enforce

        rule_id, action_order, action, duration, message = first_action
        next_action_due = datetime.utcnow()  # Use current UTC time

        # If first action is a 'wait', calculate the next action time based on the duration
        if action == "wait" and duration:
            next_action_due += timedelta(hours=int(duration))  # Add duration to the current time

        # Log the first action (step 0) with the rule_id
        cursor.execute('''
            INSERT INTO enforcement_log (community, post_id, rule_id, current_step, next_action_due)
            VALUES (?, ?, ?, ?, ?)
        ''', (community, post_id, rule_id, 0, next_action_due))

        conn.commit()

        # Now, check if the next action is due
        check_pending_enforcements()  # This will handle checking for the next due action



def check_pending_enforcements():
    
    ### TODO ###
    ### - remove function
    ### - view function
    ### - remove "print" statements
    
    
    
    with connect_to_tags_db() as conn:
        cursor = conn.cursor()
        
        # Fetch all logs to check title status
        cursor.execute('''
            SELECT id, post_id, community, rule_id, current_step, next_action_due 
            FROM enforcement_log''')  # Only get records where the action is due

        logs = cursor.fetchall()

        if not logs:
            logging.info("No pending enforcements.")
            return

        for log in logs:
            log_id, post_id, community, rule_id, current_step, next_action_due = log

            # **Step 1: Check if the post title has been updated with correct tags**
            cursor.execute('SELECT DISTINCT tags FROM enforcement_rules WHERE community = ?', (community,))
            rows = cursor.fetchall()

            if not rows:
                continue  # No enforcement rules for this community

            post_title = lemmy.post.get(post_id)['post_view']['post']['name']
            output = lemmy.comment.list(post_id=post_id)

            # Get all required tags for this community
            required_tags = set()
            for row in rows:
                required_tags.update(row[0].split(","))  # Convert stored comma-separated tags into a set
            
            # **If the post title now contains the required tags, delete the enforcement log**
            if any(tag.lower() in post_title.lower() for tag in required_tags):
                print(f"Post {post_id} in {community} now contains required tags. Deleting enforcement log.")
                cursor.execute('DELETE FROM enforcement_log WHERE id = ?', (log_id,))
                conn.commit()
                comments = lemmy.comment.list(post_id=post_id)
                for comment in comments:
                    if comment['creator']['id'] == settings.BOT_ID:
                        lemmy.comment.delete(comment['comment']['id'],deleted=True)
                
                continue  # Move on to the next log
            
        # Fetch all logs where the next action is due or overdue
        cursor.execute('''
            SELECT id, post_id, community, rule_id, current_step, next_action_due 
            FROM enforcement_log
            WHERE next_action_due <= ?
        ''', (datetime.utcnow(),))  # Only get records where the action is due

        pending_logs = cursor.fetchall()

        if not pending_logs:
            print("No pending enforcements.")
            return

        for log in pending_logs:
            log_id, post_id, community, rule_id, current_step, next_action_due = log

            # **Step 2: Fetch enforcement rule for this step**
            cursor.execute('''
                SELECT action_order, action, duration, message 
                FROM enforcement_rules 
                WHERE enforcement_id = ? AND action_order = ? 
            ''', (rule_id, current_step))
            rule = cursor.fetchone()

            if not rule:
                continue  # No rule found for this step, skip this log entry

            action_order, action, duration, message = rule

            # **Step 3: Execute enforcement action**
            execute_enforcement(community, post_id, rule_id, current_step, duration, action, message)

            # **Step 4: Determine next step**
            next_step = current_step + 1

            if action == 'wait':
                next_action_due = datetime.utcnow() + timedelta(hours=duration)
            else:
                next_action_due = datetime.utcnow()

            # **Step 5: Update enforcement log**
            cursor.execute('''
                UPDATE enforcement_log
                SET current_step = ?, next_action_due = ?
                WHERE id = ?
            ''', (next_step, next_action_due, log_id))
            conn.commit()

            # **Step 6: Check if this is the last action in the sequence**
            cursor.execute('SELECT COUNT(*) FROM enforcement_rules WHERE enforcement_id = ?', (rule_id,))
            total_steps = cursor.fetchone()[0]

            if next_step >= total_steps:
                print(f"Final action for post {post_id} reached. Deleting log entry.")
                cursor.execute('DELETE FROM enforcement_log WHERE id = ?', (log_id,))
                conn.commit()
  

def execute_enforcement(community, post_id, rule_id, current_step, duration, action, message):
    # This function will handle the enforcement action without touching the database.
    if action == 'warn':
        lemmy.comment.create(post_id, content=message)
        print(f"Warning issued for post {post_id} in community {community}")
        
    elif action == 'remove':
        # Perform the removal action
        post = lemmy.post.get(post_id)
        poster_id = post['post_view']['creator']['id']
        poster_name = post['post_view']['creator']['name']
        lemmy.private_message.create(f"{bot_strings.GREETING} {poster_name} - Your post has been removed from [{community}](/c/{community}@lemmy.zip) automatically due to not having the correct tags. You can resubmit your post, but please ensure you tag your post with the correct tags. /n/n {bot_strings.PM_SIGNOFF}", poster_id)
        lemmy.post.remove(post_id, True)
        print(f"Post {post_id} removed from community {community}.")
        
    elif action == 'wait':
        # do nothing
        print(f"Post {post_id} in community {community} will wait for {duration} hours.")
        


def store_enforcement(community, tags, steps):
    with connect_to_tags_db() as conn:
        cursor = conn.cursor()

        # Check if an enforcement set already exists for the given community
        cursor.execute('''
            SELECT id FROM enforcement_sets WHERE community = ?
        ''', (community,))
        existing_set = cursor.fetchone()

        if existing_set:
            enforcement_id = existing_set[0]

            # Delete existing enforcement rules related to this enforcement set
            cursor.execute('''
                DELETE FROM enforcement_rules WHERE enforcement_id = ?
            ''', (enforcement_id,))

            # Delete the enforcement set itself
            cursor.execute('''
                DELETE FROM enforcement_sets WHERE id = ?
            ''', (enforcement_id,))

        # Insert the new enforcement set
        cursor.execute('''
            INSERT INTO enforcement_sets (community, tags)
            VALUES (?, ?)
        ''', (community, ",".join(tags)))
        enforcement_id = cursor.lastrowid  # Get the ID of the newly inserted enforcement set

        # Insert the new enforcement rules
        for step in steps:
            action_type = step["action"]
            action_order = step["order"]
            duration = step.get("duration")  # May be None
            message = step.get("message")  # May be None

            cursor.execute('''
                INSERT INTO enforcement_rules (enforcement_id, community, tags, action_order, action, duration, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (enforcement_id, community, ",".join(tags), action_order, action_type, duration, message))

        conn.commit()

def check_post_db(post_id):
    try:
        with connect_to_mod_db() as conn:
            action_query = '''SELECT post_id FROM new_posts WHERE post_id=?'''
            post_match = execute_sql_query(conn, action_query, (post_id,))

            if post_match:
                return "duplicate"
    except Exception as e:
        logging.error("An error occurred: %s", e)
    return "error"


def add_post_to_db(post_id, poster_id, mod_action):
    try:
        logging.debug("Adding new post to db")
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO new_posts (post_id, poster_id, mod_action) VALUES (?,?,?);"""
            data_tuple = (post_id, poster_id, mod_action,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added post to db")
            return "added"

    except Exception as e:
        logging.error("An error occurred: %s", e)
    return "error"


def broadcast_message(message):
    # get lowest and highest local user ids first
    try:
        logging.debug("broadcasting message")
        with connect_to_users_db() as conn:
            cursor = conn.cursor()
            query = "SELECT public_user_id, username, subscribed FROM users ORDER BY local_user_id"
            cursor.execute(query)

            for row in cursor.fetchall():
                public_id, username, subscribed = row
                try:
                    if subscribed == 1:
                        lemmy.private_message.create(
                            bot_strings.GREETING +
                            " " +
                            username +
                            ".\n \n" +
                            message +
                            "\n\n --- \n *This is an automated message. To unsubscribe, please reply to this message with* `#unsubscribe`.",
                            public_id)
                        time.sleep(0.1)
                except Exception as e:
                    logging.exception("Message failed to send to %s", username)
    except sqlite3.Error as e:
        logging.error("SQLite error: %s", e)

    finally:
        if cursor:
            cursor.close()


def reject_user(user, rejection):
    with connect_to_users_db() as conn:
        query = "SELECT email from users WHERE local_user_id = ?"
        result = execute_sql_query(conn, query, (user,))

        email = result[0]
        logging.info("Rejection email sent to %s", email)

        message = MIMEMultipart()
        message['From'] = settings.SENDER_EMAIL
        message['To'] = email
        message['Subject'] = "Lemmy.zip - Application Rejected"

        # use this for a simple text email, uncomment below:
        body = "We've rejected your Lemmy.zip application. In order to create an inclusive, active, and spam-free Lemmy instance, we manually review each application. If you think this was a mistake, please email us at hello@lemmy.zip from the email address you created your account with and make sure to include your username, and we'll take a look. \n\n Your account was rejected for the following reason: " + rejection
        message.attach(MIMEText(body, 'plain'))

        try:
            server = smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT)
            server.starttls()
            server.login(settings.SENDER_EMAIL, settings.SENDER_PASSWORD)
            server.sendmail(settings.SENDER_EMAIL, email, message.as_string())
            logging.info("Rejection email sent successfully")
        except Exception as e:
            logging.error("Error: Unable to send email. %s", str(e))
        finally:
            server.quit()


def broadcast_status(pm_sender, status):
    with connect_to_users_db() as conn:
        cursor = conn.cursor()

        if status == "unsub":
            query = "UPDATE users SET subscribed = 0 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()
            logging.debug("User unsubscribed successfully")


        if status == "sub":
            query = "UPDATE users SET subscribed = 1 WHERE public_user_id = ?"
            cursor.execute(query, (pm_sender,))
            conn.commit()
            logging.debug("User subscribed successfully")
            
    return "successful"


def post_reports():

    recent_reports = lemmy.post.report_list(limit=5, unresolved_only="true")

    # define words in the report that will trigger the urgent message
    serious_words = settings.SERIOUS_WORDS.split(',')

    if recent_reports:
        # recent_reports = lemmy.post.report_list(limit=10)
        for report in recent_reports:
            creator = report['creator']['name']
            creator_id = report['post_report']['creator_id']
            local_user = report['creator']['local']
            report_id = report['post_report']['id']
            report_reason = report['post_report']['reason']
            # activity pub id (i.e. home instance post url)
            ap_id = report['post']['ap_id']
            reported_content_id = report['post_report']['post_id']

            report_reason = report_reason.lower()

            local_post = re.search(settings.INSTANCE, str(ap_id))
            ## REPORTS ##
            # Against content on Local instance (either by a local user or
            # remote user)
            report_reply = None
            if local_post:
                # reporter is a local user
                if local_user:
                    report_reply = bot_strings.REPORT_LOCAL
                # reporter is from a different instance
                # else:
                    # report_reply = bot_strings.REPORT_REMOTE

            with connect_to_reports_db() as conn:
                match_reports = '''SELECT report_id FROM post_reports WHERE report_id=?'''
                report_match = execute_sql_query(
                    conn, match_reports, (report_id,))

                if not report_match:
                    # tables: 'post_reports', '(report_id INT, reporter_id INT,
                    # reporter_name TEXT, report_reason TEXT, post_id INT'
                    sqlite_insert_query = """INSERT INTO post_reports (report_id, reporter_id, reporter_name, report_reason, post_id) VALUES (?,?,?,?,?);"""
                    data_tuple = (
                        report_id,
                        creator_id,
                        creator,
                        report_reason,
                        reported_content_id,
                    )
                    execute_sql_query(conn, sqlite_insert_query, data_tuple)

                    if report_reply:
                        lemmy.private_message.create(f"Hello {creator},\n\n{report_reply}\n \n{bot_strings.PM_SIGNOFF}", creator_id)

                    for word in serious_words:
                        if word in report_reason and settings.MATRIX_FLAG:
                            matrix_body = "Report from " + creator + " regarding a post at https://" + settings.INSTANCE + "/post/" + \
                                str(reported_content_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                            asyncio.run(send_matrix_message(matrix_body))
                            break


def comment_reports():
    recent_reports = lemmy.comment.report_list(limit=5, unresolved_only="true")

    # define words in the report that will trigger the urgent message
    serious_words = settings.SERIOUS_WORDS.split(',')

    if recent_reports:
        for report in recent_reports:
            creator = report['creator']['name']
            reporter_id = report['creator']['id']
            local_user = report['creator']['local']
            report_id = report['comment_report']['id']
            report_reason = report['comment_report']['reason']
            # activity pub id (i.e. home instance post url)
            ap_id = report['comment']['ap_id']
            reported_content_id = report['comment_report']['comment_id']

            report_reason = report_reason.lower()

            local_post = re.search(settings.INSTANCE, str(ap_id))

            ## REPORTS ##
            # Against content on Local instance (either by a local user or
            # remote user)
            report_reply = None
            if local_post:
                # reporter is a local user
                if local_user:
                    report_reply = bot_strings.REPORT_LOCAL
                # reporter is from a different instance
                # else:
                    # report_reply = bot_strings.REPORT_REMOTE
                else:
                    continue

            with connect_to_reports_db() as conn:
                match_reports = '''SELECT report_id FROM comment_reports WHERE report_id=?'''
                report_match = execute_sql_query(
                    conn, match_reports, (report_id,))

                if not report_match:
                    sqlite_insert_query = """INSERT INTO comment_reports (report_id, reporter_id, reporter_name, report_reason, comment_id) VALUES (?,?,?,?,?);"""
                    data_tuple = (
                        report_id,
                        reporter_id,
                        creator,
                        report_reason,
                        reported_content_id,
                    )
                    execute_sql_query(conn, sqlite_insert_query, data_tuple)

                    if report_reply:
                        lemmy.private_message.create(f"Hello {creator},\n\n{report_reply}\n \n{bot_strings.PM_SIGNOFF}", reporter_id)


                    for word in serious_words:
                        if word in report_reason and settings.MATRIX_FLAG:
                            # write message to send to matrix
                            matrix_body = "Report from " + creator + " regarding a comment at https://" + settings.INSTANCE + "/comment/" + \
                                str(reported_content_id) + ". The user gave the report reason: " + report_reason + " - Please review urgently."
                            asyncio.run(send_matrix_message(matrix_body))
                            break


def check_reports():
    post_reports()
    comment_reports()


def get_first_post_date(pd_day, pd_time, pd_frequency):
    # Map days to integers

    day = pd_day.lower()

    days = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    today = datetime.now()
    today_weekday = today.weekday()
    target_weekday = days[day]

    if pd_frequency == 'monthly':
        next_month = today + relativedelta(months=1)
        days_until_next = (target_weekday - next_month.weekday() + 7) % 7
        next_post_date = next_month + timedelta(days=days_until_next)
    else:
        days_until_next = (target_weekday - today_weekday + 7) % 7
        if days_until_next == 0 and pd_frequency != 'once':
            frequency_mapping = {
                'once': 0,
                'weekly': 7,
                'fortnightly': 14,
                '4weekly': 28
            }
            days_until_next = frequency_mapping.get(pd_frequency, 7)

        next_post_date = today + timedelta(days=days_until_next)

    post_time = datetime.strptime(pd_time, "%H:%M").time()
    return datetime.combine(next_post_date.date(), post_time)


def calc_next_post_date(old_post_date, frequency):
    frequency_mapping = {
        'once': 0,
        'weekly': timedelta(days=7),
        'fortnightly': timedelta(days=14),
        '4weekly': timedelta(days=28),
        'monthly': relativedelta(months=1)
    }

    if frequency == 'once':
        return "delete"

    time_to_add = frequency_mapping.get(frequency, timedelta(days=7))

    new_post_date = old_post_date + time_to_add

    return new_post_date


def check_scheduled_posts():
    # First get current time/date in UTC
    current_utc = datetime.now(timezone.utc)

    # second connect to DB and check all rows for a matching time/data
    # parameter
    with connect_to_autopost_db() as conn:
        cursor = conn.cursor()
        query = "SELECT pin_id, scheduled_post FROM com_posts"
        cursor.execute(query)
        records = cursor.fetchall()

        # Process each record
        for record in records:
            record_id, stored_time_str = record
            stored_datetime = datetime.fromisoformat(stored_time_str)
            stored_datetime = stored_datetime.replace(tzinfo=timezone.utc)

            # check if the stored time is within 1 minute past current UTC
            if stored_datetime <= current_utc:
                # Fetch the full row for the record_id
                full_row_query = "SELECT * FROM com_posts WHERE pin_id = ?"
                cursor.execute(full_row_query, (record_id,))
                full_row = cursor.fetchone()

                community_name = full_row[1]
                post_title = full_row[3]
                post_url = full_row[4]
                post_body = full_row[5]
                post_frequency = full_row[7]
                previous_post = full_row[8]

                if previous_post is not None:
                    lemmy.post.feature(
                        int(previous_post), False, FeatureType.Community)

                com_details = lemmy.community.get(name=community_name)

                if com_details is None:
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit()
                    continue

                if post_body is None:
                    post_body = ""
                # format body string
                post_body = post_body.replace(
                    "%m", current_utc.strftime("%B"))  # Month name
                post_body = post_body.replace(
                    "%d", current_utc.strftime("%d"))  # Day of the month
                post_body = post_body.replace(
                    "%y", current_utc.strftime("%Y"))  # Year
                post_body = post_body.replace(
                    "%w", current_utc.strftime("%A"))  # Day of the week

                # format title string
                post_title = post_title.replace(
                    "%m", current_utc.strftime("%B"))  # Month name
                post_title = post_title.replace(
                    "%d", current_utc.strftime("%d"))  # Day of the month
                post_title = post_title.replace(
                    "%y", current_utc.strftime("%Y"))  # Year
                post_title = post_title.replace(
                    "%w", current_utc.strftime("%A"))  # Day of the week

                com_id = com_details['community_view']['community']['id']
                # create post
                post_output = lemmy.post.create(
                    com_id, post_title, post_url, post_body)

                # get post ID
                previous_post = post_output['post_view']['post']['id']

                query = "UPDATE com_posts SET previous_post = ? WHERE pin_id = ?"
                cursor.execute(query, (previous_post, record_id))
                conn.commit()

                lemmy.post.feature(
                    previous_post, True, feature_type=FeatureType.Community)

                # need to work out when to make the next post
                old_post_date = stored_datetime
                next_post_date = calc_next_post_date(
                    old_post_date, post_frequency)
                # check for "once" posts
                if next_post_date == 'delete':
                    query = "DELETE FROM com_posts WHERE pin_id = ?"
                    cursor.execute(query, (record_id,))
                    conn.commit()
                    continue

                query = "UPDATE com_posts SET scheduled_post = ? WHERE pin_id = ?"
                cursor.execute(query, (next_post_date, record_id))
                conn.commit()

    # Close the database connection
    conn.close()


def log_warning(person_id, warning_message, admin):
    """
    Logs a warning into the 'warnings' table.

    Table Schema:
    - user_id (INT): ID of the person being warned.
    - warning_reason (TEXT): Reason for the warning.
    - admin (TEXT): Admin who issued the warning.
    """
    if not isinstance(person_id, int):
        raise ValueError("person_id must be an integer")
    if not warning_message or not isinstance(warning_message, str):
        raise ValueError("warning_message must be a non-empty string")
    if not admin or not isinstance(admin, str):
        raise ValueError("admin must be a non-empty string")

    try:
        with connect_to_mod_db() as conn:
            sqlite_insert_query = """INSERT INTO warnings (user_id, warning_reason, admin) VALUES (?, ?, ?);"""
            data_tuple = (person_id, warning_message, admin)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)
    except Exception as e:
        logging.info("Error logging warning: %s", e)
        raise


def get_warning_count(person_id):
    """
    Retrieves the count of warnings for a specific user ID from the 'warnings' table.

    Args:
        person_id (int): The ID of the person whose warnings need to be counted.

    Returns:
        int: The count of warnings for the specified user.

    Raises:
        ValueError: If the person_id is not an integer.
        Exception: If there is a database-related error.
    """
    if not isinstance(person_id, int):
        raise ValueError("person_id must be an integer")

    try:
        with connect_to_mod_db() as conn:
            sqlite_select_query = """SELECT COUNT(*) FROM warnings WHERE user_id = ?;"""
            cursor = conn.cursor()
            cursor.execute(sqlite_select_query, (person_id,))
            result = cursor.fetchone()
            if result:
                return result[0]
            return 0
    except Exception as e:
        logging.info("Error retrieving warning count: %s", e)
        raise

async def send_matrix_message(matrix_body):
    client = AsyncClient(settings.MATRIX_URL, settings.MATRIX_ACCOUNT)

 # use an access token to log in
    client.access_token = settings.MATRIX_API_KEY

    room_id = settings.MATRIX_ROOM_ID

    # send a message to the room
    await client.room_send(
        room_id=room_id,
        message_type="m.room.message",
        content={
            "msgtype": "m.text",
            "body": matrix_body
        }
    )

    # log out
    await client.close()


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return str(n) + suffix

def insert_block(person_id):
    
    if settings.DEFAULT_INSTANCE_BLOCKS:
        instance_blocks_list = [int(x) for x in settings.DEFAULT_INSTANCE_BLOCKS.split(',')]
    else:
        instance_blocks_list = []
    
    published = datetime.utcnow()
    
    try:    
        conn = psycopg2.connect(host=settings.DB_HOST, port=settings.DB_PORT, user=settings.DB_USER, password=settings.DB_PASSWORD, dbname=settings.DB_NAME)
        conn.autocommit = False  # Enable transaction handling
        cursor = conn.cursor()

        for instance_id in instance_blocks_list:
            # Insert new record
            cursor.execute(
                """
                INSERT INTO instance_block (person_id, instance_id, published)
                VALUES (%s, %s, %s);
                """,
                (person_id, instance_id, published),
            )

        conn.commit()  # Commit transaction
        logging.info("Default block inserted successfully!")

    except psycopg2.Error as e:
        conn.rollback()  # Rollback if an error occurs
        logging.info(f"Database error: {e}")

    finally:
        cursor.close()
        conn.close()
        
def remove_spam_message(pm_id):
    modified_content = "[Removed By Admin] - This message was likely spam. For queries please contact a member of the Admin team."
    
    try:
        with psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname=settings.DB_NAME
        ) as conn:
            with conn.cursor() as cursor:
                update_query = "UPDATE private_message SET content = %s WHERE id = %s;"
                cursor.execute(update_query, (modified_content, pm_id))
                
                logging.info(f"PM {pm_id} marked as spam and content updated.")
            conn.commit()

    except psycopg2.Error as e:
        logging.error(f"Database error: {e}")

            
def scan_private_message(pm_context, creator_id):
    spam_flag = False
    try:
        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT phrase FROM pm_spam;")
            keywords = [row[0] for row in cursor.fetchall()]
    
        for keyword in keywords:
            if keyword.lower() in pm_context.lower():
                spam_flag = True
                break

        if spam_flag:
            get_user = lemmy.user.get(creator_id)
            if not get_user:
                logging.error(f"Failed to fetch user data for ID {creator_id}")
                return "notspam"

            name = get_user['person_view']['person']['name']
            instance = get_user['site']['actor_id'].removeprefix("https://").rstrip("/")

            user_url = f"https://{settings.INSTANCE}/u/{name}@{instance}"

            logging.info(f"Account likely spam posting - {user_url}. Will ban.")
            lemmy.user.ban(ban=True, person_id=creator_id, reason="Automod Ban - Identified as a spam account", remove_data=True)

            matrix_body = f"Account likely a spam account, banning: {user_url}"
            asyncio.run(send_matrix_message(matrix_body))
            return "spam"

    except Exception as e:
        logging.error(f"Error scanning private message: {e}")

    return "notspam"


def add_pm_spam_phrase(spam_phrase):
    try:
        with connect_to_mod_db() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO pm_spam (phrase) VALUES (?);", (spam_phrase,))
            conn.commit()
            logging.info(f"Spam phrase '{spam_phrase}' added successfully.")
            matrix_body = f"New spam phrase added to PM Scanner: {spam_phrase}"
            asyncio.run(send_matrix_message(matrix_body))
            
    except sqlite3.Error as e:
        logging.error(f"Error adding spam phrase: {e}")

def check_message_bus():
    with connect_to_message_bus_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pm_scan_messages ORDER BY id LIMIT 1")
        pm_object = cursor.fetchone()

        if not pm_object:
            return

        bus_id, bot_sender, pm_id, pm_sender, pm_content = pm_object
        logging.info(f"Message on pm bus - ID:{bus_id}")

        cursor.execute("DELETE FROM pm_scan_messages WHERE id = ?", (bus_id,))
        conn.commit()

        if scan_private_message(pm_content, pm_sender) == "spam":
            remove_spam_message(pm_id)
        

