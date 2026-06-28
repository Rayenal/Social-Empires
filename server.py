import os
import json
import urllib.request
import urllib.error  # <-- هذا هو السطر الناقص السحري!
from urllib.parse import urlparse
import pg8000.dbapi
from flask import Flask, render_template, send_from_directory, request, redirect, session
from flask_cors import CORS

print(" [+] Loading basics...")
if os.name == 'nt':
    os.system("color")
    os.system("title Social Empires Server")
else:
    import sys
    sys.stdout.write("\x1b]2;Social Empires Server\x07")

print(" [+] Loading game config...")
from get_game_config import get_game_config, patch_game_config

print(" [+] Loading players...")
from get_player_info import get_player_info, get_neighbor_info
from sessions import load_saved_villages, all_saves_userid, all_saves_info, save_info, new_village, fb_friends_str

# --- إعداد الاتصال بقاعدة بيانات SUPABASE باستعمال pg8000 ---
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        try:
            # تفكيك الرابط السحابي لتوافقه مع pg8000
            url = urlparse(DATABASE_URL)
            conn = pg8000.dbapi.connect(
                user=url.username,
                password=url.password,
                host=url.hostname,
                port=url.port if url.port else 5432,
                database=url.path[1:] # حذف الفاصلة / الأولى
            )
            return conn
        except Exception as e:
            print(f" [!] Database connection error: {e}")
    return None

def init_db():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS game_data (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                ''')
                conn.commit()
            print(" [+] Supabase DB Connected and Checked successfully!")
        except Exception as e:
            print(f" [!] Error initializing DB: {e}")
        finally:
            conn.close()
    else:
        print(" [!] WARNING: Working in LOCAL mode (No DATABASE_URL provided or connection failed).")

# تشغيل الفحص عند البداية
init_db()

# دالات تعويض الملفات المحلية بـ Supabase
def supabase_get(key_name, default_factory):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM game_data WHERE key = %s;", (key_name,))
                row = cur.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            print(f" [!] Error fetching {key_name} from Supabase: {e}")
        finally:
            conn.close()
    
    # Backup محلي إذا فشل الاتصال أو كنا في طور الـ Local
    local_path = f"saves/{key_name if not key_name.endswith('.json') else key_name}"
    if os.path.exists(local_path):
        try:
            with open(local_path, 'r') as f:
                return json.load(f)
        except:
            pass
    return default_factory()

def supabase_set(key_name, data):
    # حفظ احتياطي محلي أولاً
    os.makedirs('saves', exist_ok=True)
    local_path = f"saves/{key_name if not key_name.endswith('.json') else key_name}"
    with open(local_path, 'w') as f:
        json.dump(data, f, indent=4)
        
    # حفظ سحابي في Supabase
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                json_str = json.dumps(data)
                cur.execute('''
                    INSERT INTO game_data (key, value)
                    VALUES (%s, %s)
                    ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value;
                ''', (key_name, json_str))
                conn.commit()
        except Exception as e:
            print(f" [!] Error saving {key_name} to Supabase: {e}")
        finally:
            conn.close()

# دمج الدالات القديمة مع النظام الجديد
def load_accounts():
    return supabase_get('accounts.json', dict)

def save_accounts(accounts):
    supabase_set('accounts.json', accounts)

# تعديل دالة تحميل القرى الأصلية لتقرأ من السحاب
def sync_villages_from_supabase():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM game_data WHERE key LIKE '%.json' AND key != 'accounts.json';")
                rows = cur.fetchall()
                os.makedirs('saves', exist_ok=True)
                for row in rows:
                    key, value = row[0], row[1]
                    with open(f"saves/{key}", 'w') as f:
                        f.write(value)
            print(" [+] Synchronized all villages from Supabase to local instance.")
        except Exception as e:
            print(f" [!] Sync from Supabase failed: {e}")
        finally:
            conn.close()

# مزامنة القرى قبل تشغيل السيرفر
sync_villages_from_supabase()
load_saved_villages()

print(" [+] Loading server...")
from command import command
from engine import timestamp_now
from version import version_name
from constants import Constant
from quests import get_quest_map
from bundle import ASSETS_DIR, STUB_DIR, TEMPLATES_DIR, BASE_DIR

host = '0.0.0.0'
port = int(os.environ.get("PORT", 5050))

app = Flask(__name__, template_folder=TEMPLATES_DIR)
CORS(app)
app.secret_key = 'SECRET_KEY'

##########
# ROUTES #
##########

@app.route("/", methods=['GET'])
def login():
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    return render_template("login.html", version=version_name, error=request.args.get('error'))

@app.route("/login_process", methods=['POST'])
def login_process():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    game_version = request.form.get('GAMEVERSION', 'SocialEmpires0926bsec.swf')

    if not username or not password:
        return redirect("/?error=Username and password are required!")

    accounts = load_accounts()
    if username not in accounts:
        return redirect("/?error=Account does not exist!")

    if accounts[username]['password'] != password:
        return redirect("/?error=Wrong password!")

    session['USERID'] = accounts[username]['userid']
    session['GAMEVERSION'] = game_version
    
    sync_villages_from_supabase()
    load_saved_villages()
    print(f"[LOGIN SUCCESS] Player '{username}' connected as USERID: {session['USERID']}")
    return redirect("/play.html")

@app.route("/signup_process", methods=['POST'])
def signup_process():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    empire_name = request.form.get('empire_name', '').strip()

    if not username or not password or not empire_name:
        return redirect("/?error=All fields are required!")

    if not username.isalnum():
        return redirect("/?error=Username must be alphanumeric!")

    accounts = load_accounts()
    if username in accounts:
        return redirect("/?error=Username already taken!")

    try:
        native_userid = new_village()
        user_file_name = f"{native_userid}.json"
        user_file_path = os.path.join('saves', user_file_name)
        
        if os.path.exists(user_file_path):
            with open(user_file_path, 'r') as f:
                data = json.load(f)
            data['name'] = empire_name
            
            # حفظ القرية في الـ Supabase والـ Local مع بعضهم
            supabase_set(user_file_name, data)
            
    except Exception as e:
        return redirect(f"/?error=Failed to generate village: {str(e)}")

    accounts[username] = {
        "password": password,
        "userid": native_userid
    }
    save_accounts(accounts)

    load_saved_villages()
    print(f"[REGISTER SUCCESS] Registered user '{username}' linked to native ID '{native_userid}'")
    return '''
    <script>
        alert("Your Empire has been successfully created! You can login now.");
        window.location.href = "/";
    </script>
    '''

@app.route("/play.html")
def play():
    if 'USERID' not in session or 'GAMEVERSION' not in session:
        return redirect("/")
    if session['USERID'] not in all_saves_userid():
        return redirect("/")
    
    USERID = session['USERID']
    GAMEVERSION = session['GAMEVERSION']
    return render_template("play.html", save_info=save_info(USERID), serverTime=timestamp_now(), friendsInfo=fb_friends_str(USERID), version=version_name, GAMEVERSION=GAMEVERSION, SERVERIP=host)

@app.route("/ruffle.html")
def ruffle():
    if 'USERID' not in session or 'GAMEVERSION' not in session:
        return redirect("/")
    if session['USERID'] not in all_saves_userid():
        return redirect("/")
    
    USERID = session['USERID']
    GAMEVERSION = session['GAMEVERSION']
    return render_template("ruffle.html", save_info=save_info(USERID), serverTime=timestamp_now(), version=version_name, GAMEVERSION=GAMEVERSION, SERVERIP=host)

@app.route("/new.html")
def new():
    session['USERID'] = new_village()
    session['GAMEVERSION'] = "SocialEmpires0926bsec.swf"
    return redirect("play.html")

@app.route("/crossdomain.xml")
def crossdomain():
    return send_from_directory(STUB_DIR, "crossdomain.xml")

@app.route("/img/<path:path>")
def images(path):
    return send_from_directory(TEMPLATES_DIR + "/img", path)

@app.route("/css/<path:path>")
def css(path):
    return send_from_directory(TEMPLATES_DIR + "/css", path)

## GAME STATIC
@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_projectiles.swf")
def similar_05122012_projectiles():
    return send_from_directory(ASSETS_DIR + "/swf", "20130417_projectiles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_magicParticles.swf")
def similar_05122012_magicParticles():
    return send_from_directory(ASSETS_DIR + "/swf", "20131010_magicParticles.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/swf/05122012_dynamic.swf")
def similar_05122012_dynamic():
    return send_from_directory(ASSETS_DIR + "/swf", "120608_dynamic.swf")

@app.route("/default01.static.socialpointgames.com/static/socialempires/<path:path>")
def static_assets_loader(path):
    if not os.path.exists(ASSETS_DIR + "/"+ path):
        if not os.path.exists(f"{BASE_DIR}/download_assets/assets/{path}"):
            directory = os.path.dirname(f"{BASE_DIR}/download_assets/assets/{path}")
            if not os.path.exists(directory):
                os.makedirs(directory)
            URL = f"https://static.socialpointgames.com/static/socialempires/assets/{path}"
            try:
                response = urllib.request.urlretrieve(URL, f"{BASE_DIR}/download_assets/assets/{path}")
            except urllib.error.HTTPError:
                return ("", 404)
            return send_from_directory("{BASE_DIR}/download_assets/assets", path)
        else:
            return send_from_directory("{BASE_DIR}/download_assets/assets", path)
    else:
        return send_from_directory(ASSETS_DIR, path)

## GAME DYNAMIC
@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/track_game_status.php", methods=['POST'])
def track_game_status_response():
    return ("", 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_game_config.php", methods=['GET','POST'])
def get_game_config_response():
    return get_game_config()

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_player_info.php", methods=['POST'])
def get_player_info_response():
    USERID = request.values['USERID']
    user = request.values['user'] if 'user' in request.values else None
    map = int(request.values['map']) if 'map' in request.values else None

    if user is None:
        return (get_player_info(USERID), 200)
    elif user in [Constant.NEIGHBOUR_ARTHUR_GUINEVERE_1, Constant.NEIGHBOUR_ARTHUR_GUINEVERE_2, Constant.NEIGHBOUR_ARTHUR_GUINEVERE_3]:
        return (get_neighbor_info(user, map), 200)
    elif user.startswith("100000"):
        return get_quest_map(user)
    else:
        return (get_neighbor_info(user, map), 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/sync_error_track.php", methods=['POST'])
def sync_error_track_response():
    return ("", 200)

@app.route("/null")
def flash_sync_error_response():
    return redirect("/play.html")

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/command.php", methods=['POST'])
def command_response():
    USERID = request.values['USERID']
    data_str = request.values['data']
    data = json.loads(data_str[65:])
    
    # تنفيذ الأمر الأصلي في السيرفر (تحديث الداتا محلياً أولاً)
    command(USERID, data)
    
    # بعد تنفيذ الأمر، نقوم بحفظ الملف المحدث مباشرة إلى Supabase
    user_file_name = f"{USERID}.json"
    user_file_path = os.path.join('saves', user_file_name)
    if os.path.exists(user_file_path):
        try:
            with open(user_file_path, 'r') as f:
                updated_data = json.load(f)
            supabase_set(user_file_name, updated_data)
        except Exception as e:
            print(f" [!] Sync save after command failed: {e}")
            
    return ({"result": "success"}, 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_continent_ranking.php")
def get_continent_ranking_response():
    response = {
        "world_id": 0,
        "continent": [{"posicion": i, "nivel": 1 if i==0 else 0, "user_id": 1111 if i==0 else 0} for i in range(8)]
    }
    return(response)

print(" [+] Running server...")

if __name__ == '__main__':
    app.run(host=host, port=port, debug=False)