import os
import json
import urllib
from flask import Flask, render_template, send_from_directory, request, redirect, session
from flask_cors import CORS
from flask.debughelpers import attach_enctype_error_multidict

print (" [+] Loading basics...")
if os.name == 'nt':
    os.system("color")
    os.system("title Social Empires Server")
else:
    import sys
    sys.stdout.write("\x1b]2;Social Empires Server\x07")

print (" [+] Loading game config...")
from get_game_config import get_game_config, patch_game_config

print (" [+] Loading players...")
from get_player_info import get_player_info, get_neighbor_info
from sessions import load_saved_villages, all_saves_userid, all_saves_info, save_info, new_village, fb_friends_str
load_saved_villages()

print (" [+] Loading server...")
from command import command
from engine import timestamp_now
from version import version_name
from constants import Constant
from quests import get_quest_map
from bundle import ASSETS_DIR, STUB_DIR, TEMPLATES_DIR, BASE_DIR

# تعديل الـ Host والـ Port ليتوافق مع Render ديناميكيًا
host = '0.0.0.0'
port = int(os.environ.get("PORT", 5050))

app = Flask(__name__, template_folder=TEMPLATES_DIR)
CORS(app)
app.secret_key = 'SECRET_KEY' # تفعيل الـ Session بأمان

ACCOUNTS_FILE = 'saves/accounts.json'

def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_accounts(accounts):
    os.makedirs('saves', exist_ok=True)
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=4)

print (" [+] Configuring server routes...")

##########
# ROUTES #
##########

@app.route("/", methods=['GET'])
def login():
    session.pop('USERID', default=None)
    session.pop('GAMEVERSION', default=None)
    load_saved_villages()
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

    # ربط الحساب بالـ USERID الأصلي الذي تم إنشاؤه
    session['USERID'] = accounts[username]['userid']
    session['GAMEVERSION'] = game_version
    
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

    # استعمال الدالة الأصلية للسيرفر لإنشاء قرية متوافقة 100%
    try:
        native_userid = new_village()
        
        # تعديل اسم الإمبراطورية داخل الملف الأصلي ليطابق ما اختاره اللاعب
        user_file = os.path.join('saves', f"{native_userid}.json")
        if os.path.exists(user_file):
            with open(user_file, 'r') as f:
                data = json.load(f)
            data['name'] = empire_name
            with open(user_file, 'w') as f:
                json.dump(data, f, indent=4)
    except Exception as e:
        return redirect(f"/?error=Failed to generate village: {str(e)}")

    # حفظ الحساب الجديد في ملف الحسابات
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
    command(USERID, data)
    return ({"result": "success"}, 200)

@app.route("/dynamic.flash1.dev.socialpoint.es/appsfb/socialempiresdev/srvempires/get_continent_ranking.php")
def get_continent_ranking_response():
    response = {
        "world_id": 0,
        "continent": [{"posicion": i, "nivel": 1 if i==0 else 0, "user_id": 1111 if i==0 else 0} for i in range(8)]
    }
    return(response)

print (" [+] Running server...")

if __name__ == '__main__':
    app.run(host=host, port=port, debug=False)