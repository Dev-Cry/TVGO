"""
Skript pro interakci s platformou TV GO od společnosti Telekom.
Umožňuje generovat playlist a stahovat EPG pro sledování televizního obsahu.
"""

#Verze: 1.0.0

# -*- coding:utf8;-*-

# Importování potřebných knihoven a modulů
import requests # Knihovna pro HTTP požadavky
import os # Modul pro práci se systémovými operacemi
import unicodedata # Modul pro normalizaci a kódování textu
import uuid # Modul pro generování UUID
import xmltv # Knihovna pro práci s XMLTV formátem
from urllib.parse import urlparse # Funkce pro parsování URL
from datetime import datetime, timedelta # Třídy pro práci s datumem a časem

# Globální proměnná určující zapnutí/vypnutí EPG

epg_enabled = 1  # dočasný fix pro zapnutí / vypnutí EPG

# Třída TVGO pro práci s platformou TV GO
class TVGO:
    def __init__(self, user, password, lng):
        # Inicializace třídy s uživatelskými údaji a jazykem
        self.user = user
        self.password = password
        self.lng = lng
        self.session = requests.Session() # Vytvoření nové HTTP session
        self.base_url = f"https://{self.lng}go.magio.tv"  # Základní URL pro dotazy
        self.uuid_file = os.path.join(os.path.dirname(__file__), "uuid")  # Cesta k souboru s UUID
        self.playlist_file = os.path.join(os.path.dirname(__file__), "playlist.m3u") # Cesta k souboru s playlistem
        self.epg_file = os.path.join(os.path.dirname(__file__), "epg.xml") # Cesta k souboru s EPG
        self.UA = "okhttp/3.12.12"  # User-Agent
        self.TS = self._get_current_time_suffix() # Aktuální časový prefix
        self.dev_id = self._get_device_id() # ID zařízení
        self.dev_type, self.dev_name = self._get_device_details() # Typ a název zařízení
        self.CHANNEL_IDS = "" # ID kanálů
        self.days = 7  # Počet dnů pro EPG
        self.days_back = 1 # Počet dnů zpět pro EPG
        self.channels = []  # Seznam kanálů
        self.channels2 = []  # Seznam kanálů pro XMLTV
        self.epg_enabled = 1 # Zapnutí EPG
        self.osVersion = "0.0.0" # Verze OS
        self.appVersion = "4.0.12" # Verze aplikace

    def _encode(self, string):
        # Metoda pro převod řetězce na ASCII kódování
        return unicodedata.normalize('NFKD', string).encode('ascii', 'ignore').decode("utf-8")

    def _get_current_time_suffix(self):
        # Metoda pro získání aktuálního časového prefixu
        now = datetime.now()
        local_now = now.astimezone()
        return " " + str(local_now)[-6:].replace(":", "")

    def _get_device_id(self):
        # Metoda pro získání ID zařízení
        if not os.path.exists(self.uuid_file):
            dev_id = str(uuid.uuid4())
            with open(self.uuid_file, "w") as f:
                f.write(dev_id)
        else:
            dev_id = open(self.uuid_file, "r").read()
        return dev_id
    
    def _get_device_details(self):
        # Metoda pro získání typu a názvu zařízení podle zvoleného jazyka
        if self.lng == "cz":
            return "OTT_ANDROID", "Xiaomi Mi 11"
        else:
            return "OTT_STB", "KSTB6077"

    def _make_request(self, method, url, **kwargs):
        # Metoda pro provádění HTTP požadavků
        response = None
        try:
            if method == "get":
                response = self.session.get(self.base_url + url, **kwargs)
            elif method == "post":
                response = self.session.post(self.base_url + url, **kwargs)
            elif method == "put":
                response = self.session.put(self.base_url + url, **kwargs)
            elif method == "delete":
                response = self.session.delete(self.base_url + url, **kwargs)
            else:
                raise ValueError("Unsupported HTTP method")
        except requests.RequestException as e:
            print(f"Request failed: {e}")
        return response

    def login(self):
        # Metoda pro přihlášení uživatele
        params = {
            "dsid": self.dev_id,
            "deviceName": self.dev_name,
            "deviceType": self.dev_type,
            "osVersion": self.osVersion,
            "appVersion": self.appVersion,
            "language": self.lng.upper()
        }
        headers = {"Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA}
        try:
            req_init = self._make_request("post", "/v2/auth/init", params=params, headers=headers).json()
            accessToken = req_init["token"]["accessToken"]
            params = {"loginOrNickname": self.user, "password": self.password}
            headers = {
                "Content-type": "application/json",
                "authorization": "Bearer " + accessToken,
                "Host": f"{self.lng}go.magio.tv",
                "User-Agent": self.UA,
                "Connection": "Keep-Alive"
            }
            req_login = self._make_request("post", "/v2/auth/login", json=params, headers=headers).json()
            if req_login["success"]:
                return req_login["token"]["refreshToken"]
            else:
                print("\n" + req_login["errorMessage"])
                return None
        except Exception as e:
            print(f"Login failed: {e}")
            return None

    def generate_playlist(self):
        # Metoda pro generování playlistu živých kanálů
        # Získání přihlašovacího tokenu
        refreshtoken = self.login()
        if refreshtoken is not None:
            print("Generuji playlist:")
            # Získání přístupového tokenu pomocí obnovovacího tokenu
            params = {"refreshToken": refreshtoken}
            headers = {"Content-type": "application/json", "Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA, "Connection": "Keep-Alive"}
            req = self._make_request("post", "/v2/auth/tokens", json=params, headers=headers).json()
            if req["success"]:
                accesstoken = req["token"]["accessToken"]
            else:
                print("Chyba:\n" + req["errorMessage"])
                return

            # Získání seznamu živých kanálů
            params = {"list": "LIVE", "queryScope": "LIVE"}
            headers = {"Content-type": "application/json", "authorization": "Bearer " + accesstoken, "Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA, "Connection": "Keep-Alive"}
            req = self.session.get(f"https://{self.lng}go.magio.tv/v2/television/channels", params=params, headers=headers).json()
            if req.get("items"):
                channels = []
                channels2 = []
                ids = ""
                reqq = requests.get(f"https://{self.lng}go.magio.tv/home/categories?language={self.lng}", headers=headers).json()["categories"]
                categories = {}
                for cc in reqq:
                    for c in cc["channels"]:
                        categories[c["channelId"]] = cc["name"]
                for n in req["items"]:
                    name = n["channel"]["name"]
                    logo = str(n["channel"]["logoUrl"])
                    idd = n["channel"]["channelId"]
                    ids += f",{idd}"
                    id = f"tm-{idd}-{self._encode(name).replace(' HD', '').lower().replace(' ', '-')}"
                    if not self.CHANNEL_IDS or str(idd) in self.CHANNEL_IDS.split(","):
                        channels2.append({"display-name": [(name, u"cs")], "id": str(id), "icon": [{"src": logo}]})
                        channels.append((name, idd, logo))

            # Uložení playlistu do souboru
            try:
                with open(self.playlist_file, "w", encoding="utf-8") as f:
                    f.write("#EXTM3U\n")
                    for ch in channels:
                        id = "tm-" + str(ch[1]) + str(ch[1]) + "-" + self._encode(ch[0]).replace(" HD", "").lower().replace(" ", "-")
                        if ch[1] == 5000:
                            id = "tm-6016-eurosport-1"
                        group = categories[ch[1]]
                        print(ch[0])
                        params = {
                            "service": "LIVE",
                            "name": self.dev_name,
                            "devtype": self.dev_type,
                            "id": ch[1],
                            "prof": "p5",
                            "ecid": "",
                            "drm": "verimatrix"
                        }
                        headers = {"Content-type": "application/json", "authorization": "Bearer " + accesstoken, "Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA, "Connection": "Keep-Alive"}
                        req = self.session.get(f"https://{self.lng}go.magio.tv/v2/television/stream-url", params=params, headers=headers)
                        if req.json()["success"] == True:
                            url = req.json()["url"]
                        else:
                            if req.json()["success"] == False and req.json()["errorCode"] == "NO_PACKAGE":
                                url = None
                            else:
                                print("Chyba:\n" + req.json()["errorMessage"].replace("exceeded-max-device-count", "Překročen maximální počet zařízení"))
                                if "DEVICE_MAX_LIMIT" in str(req.json()):
                                    ut = input("\nOdebrat zařízení? a/n ")
                                    if ut == "a":
                                        self.delete_device()
                                    else:
                                        return
                        if self.lng == "sk" or self.lng == "cz":
                            if url is not None:
                                headers = {"Host": urlparse(url).netloc, "User-Agent": "ReactNativeVideo/3.13.2 (Linux;Android 10) ExoPlayerLib/2.10.3", "Connection": "Keep-Alive"}
                                req = self.session.get(url, headers=headers, allow_redirects=False)
                                url = req.headers["location"]
                        if url is not None:
                            f.write('#EXTINF:-1 group-title="' + group + '" tvg-id="' + id +  '",' + str(ch[0]) + "\n" + url + '\n')
            except Exception as e:
                print(f"Failed to write playlist file: {e}")

            # Volání metody pro stažení EPG, pokud je povoleno
            if self.epg_enabled == 1:
                self.download_epg()
            else:
                print("\nHotovo\n")
                input("Pro ukončení stiskněte libovolnou klávesu")

def download_epg(self, accesstoken):
    try:
        print("\nStahuji data pro EPG:")
        programmes = []
        headers = {
            "Content-type": "application/json",
            "authorization": "Bearer " + accesstoken,
            "Host": f"{self.lng}go.magio.tv",
            "User-Agent": self.UA,
            "Connection": "Keep-Alive"
        }
        now = datetime.now()
        for i in range(self.days_back * -1, self.days):
            next_day = now + timedelta(days=i)
            back_day = (now + timedelta(days=i)) - timedelta(days=1)
            date_to = next_day.strftime("%Y-%m-%d")
            date_from = back_day.strftime("%Y-%m-%d")
            date_ = next_day.strftime("%d.%m.%Y")
            print(date_, end="", flush=True)
            req = self._make_request("get", f"/v2/television/epg?filter=channel.id=in=({','.join(str(x) for x in self.ids[1:])});endTime=ge={date_from}T23:00:00.000Z;startTime=le={date_to}T23:59:59.999Z&limit={str(len(self.channels))}&offset=0&lang={self.lng.upper()}", headers=headers).json()["items"]
            for x in range(len(req)):
                for y in req[x]["programs"]:
                    id = y["channel"]["id"]
                    name = y["channel"]["name"]
                    channel = f"tm-{id}-{self._encode(name).replace(' HD', '').lower().replace(' ', '-')}"
                    start_time = y["startTime"].replace("-", "").replace("T", "").replace(":", "")
                    stop_time = y["endTime"].replace("-", "").replace("T", "").replace(":", "")
                    title = y["program"]["title"]
                    desc = y["program"]["description"]
                    year = y["program"]["programValue"]["creationYear"] if "creationYear" in y["program"]["programValue"] else None
                    subgenre = y["program"]["programCategory"]["subCategories"][0]["desc"] if "subCategories" in y["program"]["programCategory"] else None
                    genre = [(y["program"]["programCategory"]["desc"], u''), (subgenre, u'')] if subgenre else None
                    icon = y["program"]["images"][0] if "images" in y["program"] and y["program"]["images"] else None
                    epi = y["program"]["programValue"]["episodeId"] if "episodeId" in y["program"]["programValue"] else None
                    if epi is not None:
                        title = f"{title} ({epi})"
                    try:
                        programm = {
                            'channel': str(channel),
                            'start': start_time + self.TS,
                            'stop': stop_time + self.TS,
                            'title': [(title, u'')],
                            'desc': [(desc, u'')]
                        }
                        if year is not None:
                            programm['date'] = year
                        if genre is not None:
                            programm['category'] = genre
                        if icon is not None:
                            programm['icon'] = [{"src": icon}]
                    except Exception as e:
                        print(f"Failed to process program: {e}")
                    if programm not in programmes:
                        programmes.append(programm)
            print("  OK")
        print("\nGeneruji EPG")
        w = xmltv.Writer(encoding="utf-8", source_info_url="http://www.funktronics.ca/python-xmltv", source_info_name="Funktronics", generator_info_name="python-xmltv", generator_info_url="http://www.funktronics.ca/python-xmltv")
        for c in self.channels2:
            w.addChannel(c)
        for p in programmes:
            w.addProgramme(p)
        w.write(self.epg_file, pretty_print=True)
        print("Hotovo\n")
        input("Pro ukončení stiskněte libovolnou klávesu")
    except Exception as e:
        print(f"Failed to download EPG: {e}")

def delete_device(self):
        refreshtoken = self.login()
        if refreshtoken is not None:
            params = {"refreshToken": refreshtoken}
            headers = {"Content-type": "application/json", "Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA, "Connection": "Keep-Alive"}
            req = self._make_request("post", "/v2/auth/tokens", json=params, headers=headers).json()
            if req["success"] == True:
                accesstoken = req["token"]["accessToken"]
            else:
                print("Chyba:\n" + req["errorMessage"])
                return
            headers = {"Content-type": "application/json", "authorization": "Bearer " + accesstoken, "Host": f"{self.lng}go.magio.tv", "User-Agent": self.UA, "Connection": "Keep-Alive"}
            req = self._make_request("get", "/v2/home/my-devices", headers=headers).json()
            devices = []
            try:
                devices.append((req["thisDevice"]["name"] + " (Toto zařízení)", req["thisDevice"]["id"]))
            except:
                pass
            try:
                for d in req["smallScreenDevices"]:
                    devices.append((d["name"], d["id"]))
            except:
                pass
            try:
                for d in req["stbAndBigScreenDevices"]:
                    devices.append((d["name"], d["id"]))
            except:
                pass
            os.system('cls||clear')
            i = 0
            for x in devices:
                print('{:30s} {:1s} '.format(x[0], str(i)))
                i+=1
            try:
                l = int(input("\nVyberte zařízení:\n"))
                dev_id = devices[l][1]
                req = self._make_request("get", f"/home/deleteDevice?id={str(dev_id)}", headers=headers).json()
                if req["success"] == True:
                    os.system('cls||clear')
                    print("Odebráno\n")
                    self.generate_playlist()
                else:
                    os.system('cls||clear')
                    print("Chyba:\n" + req["errorMessage"])
            except:
                os.system('cls||clear')
                print("Chyba")
            return

if __name__ == "__main__":
    # Příklad použití třídy TVGO
    user = "TV136561894"
    password = "w1b0T9"
    lng = "cz"

    tvgo = TVGO(user, password, lng)
    tvgo.login()
    tvgo.generate_playlist()
    tvgo.download_epg()
