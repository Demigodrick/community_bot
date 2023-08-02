from pythorhead import Lemmy
from pythorhead.types import SortType, ListingType
from config import settings
import logging
import sqlite3
import time
import requests
import json


## TODO
## - finish polls (closure)


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def login():
    global lemmy
    lemmy = Lemmy("https://" + settings.INSTANCE)
    lemmy.log_in(settings.USERNAME, settings.PASSWORD)

    return lemmy

def create_table(conn, table_name, table_definition):
    curs = conn.cursor()
    curs.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} {table_definition}''')
    conn.commit()
    logging.debug(f"Checked/created {table_name} table")

def check_dbs():
    try:
        with sqlite3.connect('resources/vote.db') as conn:
            # Create or check votes table
            create_table(conn, 'votes', '(vote_id INT, username TEXT, vote_result TEXT)')

            # Create or check polls table
            create_table(conn, 'polls', '(poll_id INT, poll_name TEXT, username TEXT, open TEXT)')

        with sqlite3.connect('resources/users.db') as conn:
            #Create or check users table
            create_table(conn, 'users', '(local_user_id INT, public_user_id INT, username TEXT, has_posted INT, has_had_pm INT, email TEXT)')

            #Create or check communities table
            create_table(conn, 'communities', '(community_id INT, community_name TEXT)')

        with sqlite3.connect('resources/games.db') as conn:
            #create or check bundles table
            create_table(conn, 'bundles', '(bundle_machine_name TEXT)')

    except sqlite3.Error as e:
        logging.error(f"Database error: {e}")
    except Exception as e:
        logging.error(f"Exception in _query: {e}")
  
def connect_to_vote_db():
    return sqlite3.connect('resources/vote.db')

def execute_sql_query(connection, query, params=()):
    with connection:
        curs = connection.cursor()
        curs.execute(query, params)
        return curs.fetchone()

def add_vote_to_db(pm_username, vote_id, vote_response):
    try:
        with connect_to_vote_db() as conn:
            # Check vote_id (poll_id in polls table) is valid
            poll_query = '''SELECT poll_id, poll_name FROM polls WHERE poll_id=?'''
            check_valid = execute_sql_query(conn, poll_query, (vote_id,))

            if check_valid is None:
                logging.debug("Submitted vote_id did not match a valid poll_id")
                return "notvalid"
            poll_name = check_valid[1]

            # Check if vote response is already recorded for this user/vote id
            vote_query = '''SELECT vote_id, username FROM votes WHERE vote_id=? AND username=?'''
            row = execute_sql_query(conn, vote_query, (vote_id, pm_username))

            if row:
                logging.debug("Matching vote found")
                return "duplicate"

            # If no duplicate votes, add new vote
            sqlite_insert_query = """INSERT INTO votes (vote_id, username, vote_result) VALUES (?, ?, ?);"""
            data_tuple = (vote_id, pm_username, vote_response)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added vote to database")
            return poll_name
    except Exception as e:
        logging.error(f"An error occurred: {e}")
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

            logging.debug("Added poll to database with ID number " + str(poll_id))
            return poll_id
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"

def check_pms():
    try:
        pm = lemmy.private_message.list(True, 1)

        private_messages = pm['private_messages']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for pm in private_messages:
        pm_sender = pm['private_message']['creator_id']
        pm_username = pm['creator']['name']
        pm_context = pm['private_message']['content']
        pm_id = pm['private_message']['id']

        output = lemmy.user.get(pm_sender)
        user_score = output['person_view']['counts']['comment_score']
        user_local = output['person_view']['person']['local']
        user_admin = output['person_view']['person']['admin']

        logging.debug(pm_username + " (" + str(pm_sender) + ") sent " + pm_context + " - user score is " + str(user_score) + " " + str(user_admin))

        if user_local != settings.LOCAL:
            lemmy.private_message.create("Hey, " + pm_username + f". This bot is only for users of {settings.INSTANCE}. "
                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#help":
            if user_admin == True:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules."
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n\n As an Admin, you also have access to the following commands: \n"
                                                                            "- `#poll` - Create a poll for users to vote on. Give your poll a name, and you will get back an ID number to users so they can vote on your poll. Example usage: `#poll @Vote for best admin` \n"
                                                                            "- `#closepoll` - Close an existing poll using the poll ID number, for example `#closepoll @1`" 
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". These are the commands I currently know:" + "\n\n "
                                                                            "- `#help` - See this message. \n "
                                                                            "- `#rules` - See the current instance rules."
                                                                            "- `#score` - See your user score. \n "
                                                                            "- `#create` - Create a new community. Use @ to specify the name of the community you want to create, for example `#create @bot_community`. \n"
                                                                            "- `#vote` - Vote on an active poll. You'll need to have a vote ID number. An example vote would be `#vote @1 @yes` or `#vote @1 @no`.\n" 
                                                                            "- `#credits` - See who spent their time making this bot work!"
                                                                            "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context == "#score":
            lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is " + str(user_score) + ". \n \n I am a Bot. If you have any "
                                                                "queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context == "#rules":
            lemmy.private_message.create("Hey, " + pm_username + ". These are the current rules for Lemmy.zip. \n \n"
                                                                    "- Please abide by the [General Code of Conduct](https://join-lemmy.org/docs/en/code_of_conduct.html) at all times.\n"
                                                                    "- Remember the human! (no harassment, threats, etc.)\n"
                                                                    "- No racism or other discrimination\n"
                                                                    "- No endorsement of hate speech\n"
                                                                    "- No self-advertisements or spam\n"
                                                                    "- No link-spamming\n"
                                                                    "- No content against UK law.\n"
                                                                    "- Any NSFW post must be tagged as NSFW. Failure to do so will be given one warning only\n"
                                                                    "- Anything that you wouldn’t want your boss or coworkers to see, needs to be tagged NSFW\n"
                                                                    "- NSFW also acts as “Content Warning” outside of the specific NSFW communities\n\n"
                                                                    "Any posts or comments that are in breach of these rules will be dealt with, and remediation will occur. Whether that be a warning, temporary ban, or permanent ban.\n\n"
                                                                    "(TLDR) The crux of it boils down to:\n"
                                                                    "- Remember that we are all humans\n"
                                                                    "- Don’t be overtly aggressive towards anyone\n"
                                                                    "- Try and share ideas, thoughts and criticisms in a constructive way\n"
                                                                    "- Tag any NSFW posts as such"                                       
                                                                    "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context == "#credits":
            lemmy.private_message.create("Hey, " + pm_username + ". This bot was built with help and support from various community members and contributers: \n\n"
                                                                "- Demigodrick - Original Creator\n"
                                                                "- Sami - Support with original idea and implementation \n"
                                                                "- TheDuude (sh.itjust.works) - Refactoring of code and support with improving inital implementation \n"
                                                                "- efwis - code contributions regarding new user database \n\n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue


        if pm_context.split(" @")[0] == "#create":
            community_name = pm_context.split("@")[1]

            # check user score
            if user_score < int(settings.SCORE):
                lemmy.private_message.create("Hey, " + pm_username + ". Your comment score is too low to create a "
                                                                        "community. Please interact with other "
                                                                        "communities first. You can check your score at "
                                                                        "any time by sending me a message with `#score` "
                                                                        "and I will let you know!"  "\n \n I am a Bot. "
                                                                        "If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # check if it already exists
            check_community = lemmy.discover_community(community_name)

            if check_community is not None:
                lemmy.private_message.create("Hey, " + pm_username + ". Sorry, it looks like the community you are "
                                                                        "trying to create already exists. \n \n I am a "
                                                                        "Bot. If you have any queries, please contact ["
                                                                        "Demigodrick](/u/demigodrick@lemmy.zip) or ["
                                                                        "Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            # create community - add user and remove bot as mod
            lemmy.community.create(community_name, community_name)
            community_id = lemmy.discover_community(community_name)
            lemmy.community.add_mod_to_community(True, community_id, pm_sender)
            lemmy.community.add_mod_to_community(False, community_id, settings.BOT_ID)

            lemmy.private_message.create("Hey, " + pm_username + ". Your new community, [" + community_name + "](/c/" + community_name + "), has been created. You can now set this community up to your liking. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

        if pm_context.split(" @")[0] == "#vote":
            vote_id = pm_context.split("@")[1]
            vote_response = pm_context.split("@")[2]

            db_response = add_vote_to_db(pm_username,vote_id,vote_response) 

            if db_response == "duplicate":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It looks like you've already voted on this poll. Votes can only be counted once. " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            if db_response == "notvalid":
                lemmy.private_message.create("Hey, " + pm_username + ". Oops! It doesn't look like the poll you've tried to vote on exists. Please double check the vote ID and try again." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue

            else:
                lemmy.private_message.create("Hey, " + pm_username + ". Your vote has been counted on the '" + db_response + "' poll . Thank you for voting! " 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
                continue


        if pm_context.split(" @")[0] == "#poll":
            if user_admin == True:
                poll_name = pm_context.split("@")[1]
                poll_id = create_poll(poll_name, pm_username) 
                lemmy.private_message.create("Hey, " + pm_username + ". Your poll has been created with ID number " + str(poll_id) + ". You can now give this ID to people and they can now cast a vote using the `#vote` operator." 
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)
            else:
                lemmy.private_message.create("Hey, " + pm_username + ". You need to be an instance admin in order to create a poll."
                                                                 "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", pm_sender)
                lemmy.private_message.mark_as_read(pm_id, True)


        #keep this at the bottom
        else:
            lemmy.private_message.create("Hey, " + pm_username + ". Sorry, I did not understand your request. Please "
                                                                 "try again or use `#help` for a list of commands. \n "
                                                                 "\n I am a Bot. If you have any queries, "
                                                                 "please contact [Demigodrick]("
                                                                 "/u/demigodrick@lemmy.zip) or [Sami]("
                                                                 "/u/sami@lemmy.zip). Beep Boop.", pm_sender)
            lemmy.private_message.mark_as_read(pm_id, True)
            continue

def is_spam_email(email, spam_domains):
    # Split the email address at '@' and take the second half (i.e., the domain)
    domain = email.split('@')[1]
    # Check if the domain is in the list of spam domains
    return domain in spam_domains

def get_new_users():
    spam_domains = set()  # Initialize an empty set

    # Read in the list of spam domains from a file
    with open('resources/disposable_email_blocklist.conf', 'r') as file:
        for line in file:
            spam_domains.add(line.strip())  # Add each domain to the set

    try:
        output = lemmy.admin.list_applications(unread_only="true")
        new_apps = output['registration_applications']
    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for output in new_apps:
        local_user_id = output['registration_application']['local_user_id']
        username = output['creator']['name']
        email = output['creator_local_user']['email']
        public_user_id = output['creator_local_user']['person_id']
       
        if update_registration_db(local_user_id, username, public_user_id, email) == "new_user":
            logging.debug("sending new user a pm")
            lemmy.private_message.create("Hey, " + username + ". \n \n # Welcome to Lemmy.zip! \n \n Please take a moment to familiarise yourself with [our Welcome Post](https://lemmy.zip/post/43)." 
                                                                "This post has all the information you'll need to get started on Lemmy, so please have a good read first! \n \n"
                                                                "Please also take a look at our rules, they are in the sidebar of this instance. I can send these to you at any time, just send me a message with `#rules`. \n \n"
                                                                "If you're on a mobile device, you can [tap here](https://m.lemmy.zip) to go straight to our mobile site. \n \n"
                                                                "Lemmy.zip is 100% funded by user donations, so if you are enjoying your time on Lemmy.zip please [consider donating](https://opencollective.com/lemmyzip).\n \n"
                                                                "If you'd like more help, please reply to this message with `#help` for a list of things I can help with. \n \n"
                                                                "I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip) via email to `hello@lemmy.zip`. Beep Boop. ", public_user_id)
            
            # Check if the email is from a known spam domain     
            if is_spam_email(email, spam_domains):
                logging.info(f"User {username} tried to register with a spam email: {email}")
                lemmy.private_message.create("Hello, new user " + username + " with ID " + str(public_user_id) + " has signed up with a temporary/spam email address. Please manually review before approving.", 2)
                lemmy.private_message.create("Hello, new user " + username + " with ID " + str(public_user_id) + " has signed up with a temporary/spam email address. Please manually review before approving.", 16340)
        continue

def update_registration_db(local_user_id, username, public_user_id, email):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            #search db for matching user id
            curs.execute('SELECT local_user_id FROM users WHERE local_user_id=?', (local_user_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching ID found, ignoring")
                return "User ID already exists"

            logging.debug("User ID did not match an existing user ID, adding")       
            sqlite_insert_query = "INSERT INTO users (local_user_id, public_user_id, username, email) VALUES (?, ?, ?, ?);"
            data_tuple = (local_user_id, public_user_id, username, email)
            
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
        communities = lemmy.community.list(limit=5, page=1, sort=SortType.New, type_=ListingType.Local)
        local_comm = communities

    except:
        logging.info("Error with connection, retrying...")
        login()
        return

    for communities in local_comm:
        community_id = communities['community']['id']
        community_name = communities['community']['name']
        
        find_mod = lemmy.community.get(community_id)
        mods = find_mod['moderators']

        #throwing this in here to help stop nginx timeouts causing errors
        time.sleep(0.5)

        for find_mod in mods:
            mod_id = find_mod['moderator']['id']
            mod_name = find_mod['moderator']['name']

        if new_community_db(community_id, community_name) == "community":
            lemmy.private_message.create("Hey, " + mod_name + ". Congratulations on creating your community, [" + community_name + "](/c/"+community_name+"@lemmy.zip). \n Here are some tips for getting users to subscribe to your new community!\n"
                                                                "- Try posting a link to your community at [New Communities](/c/newcommunities@lemmy.world).\n"
                                                                "- Ensure your community has some content. Users are more likely to subscribe if content is already available.(5 to 10 posts is usually a good start)\n"
                                                                "- Consistency is key - you need to post consistently and respond to others to keep engagement with your new community up.\n\n"
                                                                "I hope this helps!"
                                                                "\n \n I am a Bot. If you have any queries, please contact [Demigodrick](/u/demigodrick@lemmy.zip) or [Sami](/u/sami@lemmy.zip). Beep Boop.", mod_id)    


def new_community_db(community_id, community_name):
    try:
        with sqlite3.connect('resources/users.db') as conn:
            curs = conn.cursor()

            #search db to see if community exists in DB already
            curs.execute('SELECT community_id FROM communities WHERE community_id=?', (community_id,))
            id_match = curs.fetchone()

            if id_match is not None:
                logging.debug("Matching community ID found, ignoring")
                return "Community ID already exists"

            logging.debug("community ID did not match an existing community ID, adding")       
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
    
def humblebundle():
    response = requests.get("https://www.humblebundle.com/client/bundles")
    bundles = json.loads(response.text)
    for bundle in bundles:
        bundle_url = bundle['url']
        bundle_name = bundle['bundle_name']
        bundle_machine_name = bundle['bundle_machine_name']

        if (".com/games" not in bundle_url) and (".com/membership" not in bundle_url):
            continue

        #add or check bundle in db
        if add_bundle_to_db(bundle_machine_name) == "added":
            #add bundle to website
            community_id = lemmy.discover_community("gamedeals")
            lemmy.post.create(community_id,name="Humble Bundle: " + bundle_name, url=bundle_url)


def connect_to_games_db():
    return sqlite3.connect('resources/games.db')

def add_bundle_to_db(bundle_machine_name):
    try:
        with connect_to_games_db() as conn:
            # Check if bundble already is in db
            bundle_query = '''SELECT bundle_machine_name FROM bundles WHERE bundle_machine_name=?'''
            bundle_match = execute_sql_query(conn, bundle_query, (bundle_machine_name,))

            if bundle_match:
                return "duplicate"

            logging.debug("New bundle to be added to DB")
            
            sqlite_insert_query = """INSERT INTO bundles (bundle_machine_name) VALUES (?);"""
            data_tuple = (bundle_machine_name,)
            execute_sql_query(conn, sqlite_insert_query, data_tuple)

            logging.debug("Added bundle to database")
            return "added"
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        return "error"