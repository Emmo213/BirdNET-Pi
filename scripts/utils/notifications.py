import apprise
import html
import os
import requests
import socket
import sqlite3
import time as timeim

from datetime import datetime

userDir = os.path.expanduser('~')
APPRISE_CONFIG = userDir + '/BirdNET-Pi/apprise.txt'
APPRISE_CONFIG_TEST = userDir + '/BirdNET-Pi/apprise_test.txt'
DB_PATH = userDir + '/BirdNET-Pi/scripts/birds.db'

flickr_images = {}
species_last_notified = {}

asset = apprise.AppriseAsset(
    plugin_paths=[
        userDir + "/.apprise/plugins",
        userDir + "/.config/apprise/plugins",
    ]
)
apobj = apprise.Apprise(asset=asset)
config = apprise.AppriseConfig()
config.add(APPRISE_CONFIG)
apobj.add(config)


def notify(body, title, attached=""):
    if attached != "":
        apobj.notify(
            body=body,
            title=title,
            attach=attached,
        )
    else:
        apobj.notify(
            body=body,
            title=title,
        )


def sendAppriseNotifications(species, confidence, confidencepct, path,
                             date, time, week, latitude, longitude, cutoff,
                             sens, overlap, settings_dict, db_path=DB_PATH, test_msg=False):
    def render_template(template, reason=""):
        ret = template.replace("$sciname", sciName) \
            .replace("$comname", comName) \
            .replace("$confidencepct", confidencepct) \
            .replace("$confidence", confidence) \
            .replace("$listenurl", listenurl) \
            .replace("$friendlyurl", friendlyurl) \
            .replace("$date", date) \
            .replace("$time", time) \
            .replace("$week", week) \
            .replace("$latitude", latitude) \
            .replace("$longitude", longitude) \
            .replace("$cutoff", cutoff) \
            .replace("$sens", sens) \
            .replace("$flickrimage", image_url if "{" in body else "") \
            .replace("$wikiurl", wikiurl) \
            .replace("$overlap", overlap) \
            .replace("$reason", reason)
        return ret
    # print(sendAppriseNotifications)
    # print(settings_dict)

    if (os.path.exists(APPRISE_CONFIG) and os.path.getsize(APPRISE_CONFIG) > 0) or \
       (os.path.exists(APPRISE_CONFIG_TEST) and os.path.getsize(APPRISE_CONFIG_TEST)) > 0:

        title = html.unescape(settings_dict.get('APPRISE_NOTIFICATION_TITLE'))
        body = html.unescape(settings_dict.get('APPRISE_NOTIFICATION_BODY'))

        sciName, comName = species.split("_")

        APPRISE_ONLY_NOTIFY_SPECIES_NAMES = settings_dict.get('APPRISE_ONLY_NOTIFY_SPECIES_NAMES')
        if APPRISE_ONLY_NOTIFY_SPECIES_NAMES is not None and APPRISE_ONLY_NOTIFY_SPECIES_NAMES.strip() != "":
            if any(bird.lower().replace(" ", "") in comName.lower().replace(" ", "") for bird in APPRISE_ONLY_NOTIFY_SPECIES_NAMES.split(",")):
                return

        APPRISE_ONLY_NOTIFY_SPECIES_NAMES_2 = settings_dict.get('APPRISE_ONLY_NOTIFY_SPECIES_NAMES_2')
        if APPRISE_ONLY_NOTIFY_SPECIES_NAMES_2 is not None and APPRISE_ONLY_NOTIFY_SPECIES_NAMES_2.strip() != "":
            if not any(bird.lower().replace(" ", "") in comName.lower().replace(" ", "") for bird in APPRISE_ONLY_NOTIFY_SPECIES_NAMES_2.split(",")):
                return

        APPRISE_MINIMUM_SECONDS_BETWEEN_NOTIFICATIONS_PER_SPECIES = settings_dict.get('APPRISE_MINIMUM_SECONDS_BETWEEN_NOTIFICATIONS_PER_SPECIES')
        if APPRISE_MINIMUM_SECONDS_BETWEEN_NOTIFICATIONS_PER_SPECIES != "0":
            if species_last_notified.get(comName) is not None:
                try:
                    if int(timeim.time()) - species_last_notified[comName] < int(APPRISE_MINIMUM_SECONDS_BETWEEN_NOTIFICATIONS_PER_SPECIES):
                        return
                except Exception as e:
                    print("APPRISE NOTIFICATION EXCEPTION: "+str(e))
                    return

        # TODO: this all needs to be changed, we changed the caddy default to allow direct IP access, so birdnetpi.local shouldn't be relied on anymore
        try:
            websiteurl = settings_dict.get('BIRDNETPI_URL')
            if len(websiteurl) == 0:
                raise ValueError('Blank URL')
        except Exception:
            websiteurl = "http://"+socket.gethostname()+".local"

        listenurl = websiteurl+"?filename="+path
        friendlyurl = "[Listen here]("+listenurl+")"
        wikiurl = "https://wikipedia.org/wiki/" + sciName.replace(' ', '_')
        image_url = ""

        if len(settings_dict.get('FLICKR_API_KEY')) > 0 and "$flickrimage" in body:
            if comName not in flickr_images:
                try:
                    # TODO: Make this work with non-english comnames. Implement the "// convert sci name to English name" logic from overview.php here
                    headers = {'User-Agent': 'Python_Flickr/1.0'}
                    url = ('https://www.flickr.com/services/rest/?method=flickr.photos.search&api_key=' + str(settings_dict.get('FLICKR_API_KEY')) +
                           '&text=' + str(comName) + ' bird&sort=relevance&per_page=5&media=photos&format=json&license=2%2C3%2C4%2C5%2C6%2C9&nojsoncallback=1')
                    resp = requests.get(url=url, headers=headers, timeout=10)

                    resp.encoding = "utf-8"
                    data = resp.json()["photos"]["photo"][0]

                    image_url = 'https://farm'+str(data["farm"])+'.static.flickr.com/'+str(data["server"])+'/'+str(data["id"])+'_'+str(data["secret"])+'_n.jpg'
                    flickr_images[comName] = image_url
                except Exception as e:
                    print("FLICKR API ERROR: "+str(e))
                    image_url = ""
            else:
                image_url = flickr_images[comName]

        if test_msg:
            apobj.clear()
            config.clear()
            config.add(APPRISE_CONFIG_TEST)
            apobj.add(config)

            notify_body = render_template(body, "Test message")
            notify_title = render_template(title, "Test message")
            notify(notify_body, notify_title, image_url)

            apobj.clear()
            config.clear()
            config.add(APPRISE_CONFIG)
            apobj.add(config)

            os.remove(APPRISE_CONFIG_TEST)
            return

        if settings_dict.get('APPRISE_NOTIFY_EACH_DETECTION') == "1":
            notify_body = render_template(body, "detection")
            notify_title = render_template(title, "detection")
            notify(notify_body, notify_title, image_url)
            species_last_notified[comName] = int(timeim.time())

        APPRISE_NOTIFICATION_NEW_SPECIES_DAILY_COUNT_LIMIT = 1  # Notifies the first N per day.
        if settings_dict.get('APPRISE_NOTIFY_NEW_SPECIES_EACH_DAY') == "1":
            try:
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                cur.execute(f"SELECT DISTINCT(Com_Name), COUNT(Com_Name) FROM detections WHERE Date = DATE('{today}') GROUP BY Com_Name")
                known_species = cur.fetchall()
                detections = [d[1] for d in known_species if d[0] == comName.replace("'", "")]
                numberDetections = 0
                if len(detections):
                    numberDetections = detections[0]
                if numberDetections > 0 and numberDetections <= APPRISE_NOTIFICATION_NEW_SPECIES_DAILY_COUNT_LIMIT:
                    print("send the notification")
                    notify_body = render_template(body, "first time today")
                    notify_title = render_template(title, "first time today")
                    notify(notify_body, notify_title, image_url)
                    species_last_notified[comName] = int(timeim.time())
                con.close()
            except sqlite3.Error as e:
                print(e)
                print("Database busy")
                timeim.sleep(2)

        if settings_dict.get('APPRISE_NOTIFY_NEW_SPECIES') == "1":
            try:
                con = sqlite3.connect(db_path)
                cur = con.cursor()
                today = datetime.now().strftime("%Y-%m-%d")
                cur.execute(f"SELECT DISTINCT(Com_Name), COUNT(Com_Name) FROM detections WHERE Date >= DATE('{today}', '-7 day') GROUP BY Com_Name")
                known_species = cur.fetchall()
                detections = [d[1] for d in known_species if d[0] == comName.replace("'", "")]
                numberDetections = 0
                if len(detections):
                    numberDetections = detections[0]
                if numberDetections > 0 and numberDetections <= 5:
                    reason = f"only seen {numberDetections} times in last 7d"
                    notify_body = render_template(body, reason)
                    notify_title = render_template(title, reason)
                    notify(notify_body, notify_title, image_url)
                    species_last_notified[comName] = int(timeim.time())
                con.close()
            except sqlite3.Error:
                print("Database busy")
                timeim.sleep(2)


if __name__ == "__main__":
    print("notfications")
