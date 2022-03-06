"""
"""

import mariadb as mdb
import os
import re
import random, string
from PIL import Image, ImageOps, ExifTags
import ffmpeg
import logging
import mimetypes
import dateutil.parser as parser

import config

# Casting support:
import pychromecast as cc
import threading
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler

__version__ = '0.1.0'

dbconfig = {
    'host': 'localhost',
    'user': config.MDB_USER,
    'password': config.MDB_PWD,
    'database': config.MDB_DBNAME
}

exif_ids = {
    'Make': 271,
    'Model': 272,
    'Orientation': 274,
    'GPSInfo': 34853,
    'DateTimeOriginal': 36867,
    'Flash': 37385,
    'ExifImageWidth': 40962,
    'ExifImageHeight': 40963,
}

class MedievalDB:
    def __init__(self, *args, **kwargs):
        try:
            db = mdb.connect(**dbconfig)
            self.cursor = db.cursor(dictionary=True) # for mariadb module
            db.autocommit = True
        except mdb.Error as e:
            logging.critical(f'error connecting to the database: {e}')
            exit(1)

        if not os.path.exists(config.THUMBNAIL_DIR):
            os.makedirs(config.THUMBNAIL_DIR, mode=0o755, exist_ok=True)

    def create_empty_database(self, overwrite=False):
        """
        @overwrite: delete existing database entries (default: False)

        Creates tables in the database. If @overwrite is set to True, it deletes
        any previous database entries.
        """

        if overwrite:
            self.cursor.execute('drop table if exists albums_in_collections')
            self.cursor.execute('drop table if exists media_in_albums')
            self.cursor.execute('drop table if exists media')
            self.cursor.execute('drop table if exists collections')
            self.cursor.execute('drop table if exists albums')
        
        self.cursor.execute('create table media (id int unsigned not null auto_increment primary key, filename varchar(256) not null, thumbnail varchar(32) not null, mimetype varchar(32), timestamp datetime, width smallint unsigned, height smallint unsigned, orientation tinyint, make varchar(32), model varchar(32))')
        self.cursor.execute('create table collections (id int unsigned not null auto_increment, name varchar(16) not null, password char(64) default NULL, primary key(id))')
        self.cursor.execute('create table albums (id int unsigned not null auto_increment, name varchar(100) not null, password char(64) default NULL, primary key(id))')
        self.cursor.execute('create table media_in_albums (album_id int unsigned not null, media_id int unsigned not null, foreign key (album_id) references albums(id), foreign key (media_id) references media(id), unique (album_id, media_id))')
        self.cursor.execute('create table albums_in_collections (collection_id int unsigned not null, album_id int unsigned not null, foreign key (collection_id) references collections(id), foreign key (album_id) references albums(id), unique (collection_id, album_id))')

    def generate_thumbnail(self, filename, image):
        thname = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        image.thumbnail((256, 256), Image.ANTIALIAS)
        oriented_image = ImageOps.exif_transpose(image)
        oriented_image.save(config.THUMBNAIL_DIR + f'/{thname}.jpg')

        return thname

    def generate_video_thumbnail(self, filename, width, height, duration):
        thname = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        xsize = 256 if width >= height else -1
        ysize = -1 if width >= height else 256
        
        capture = ffmpeg.input(filename, ss=duration // 2).filter('scale', xsize, ysize).output(config.THUMBNAIL_DIR + f'/{thname}.jpg', vframes=1).overwrite_output().run(capture_stdout=True, capture_stderr=True)
        return thname

    def get_video_timestamp(self, metadata):
        """
        Alas, there seems to be no clear standard for including timestamps in
        the videos. Here we try several common options in the hope that
        something will work.
        """

        # regex rules:
        regex_rules = [r'\d{8}.\d{6}', r'\d{8}']

        # try creation time:
        tags = metadata['format'].get('tags', None)
        if tags:
            ct = metadata['format']['tags'].get('creation_time', None)
            if ct:
                iso = parser.parse(ct)
                return f'{iso.date()} {iso.time()}'

        # try the filename:
        filename = metadata['format'].get('filename', None)
        if filename:
            for rule in regex_rules:
                match = re.search(rule, filename)
                if match is None:
                    continue
                print(match.start(), match.end())
                iso = parser.parse(filename[match.start():match.end()].replace('_', '-'))
                return f'{iso.date()} {iso.time()}'

        return 'NULL'

    def media_in_database(self, filename):
        self.cursor.execute(f'select * from media where filename="{filename}"')
        entries = self.cursor.fetchall()
        return False if len(entries) == 0 else True

    def import_media_from_directory(self, path):
        media_ids = []

        files = os.listdir(path)
        for file in files:
            filename = os.path.abspath(path+'/'+file)

            # check if the file is already in the database:
            if self.media_in_database(filename):
                logging.info(f'media {filename} already in the database, skipping.')
                continue

            mimetype = mimetypes.guess_type(filename)[0]
            if mimetype is None:
                logging.info(f'file {filename} has no identifiable mime type, skipping.')
                continue

            if 'image' in mimetype:
                try:
                    im = Image.open(filename)
                    exif = import_exif(im)
                except:
                    logging.info(f'failed to import {filename}, skipping.')
                    continue

                timestamp = exif.get('DateTimeOriginal', 'NULL')
                width = exif.get('ExifImageWidth', im.size[0])
                height = exif.get('ExifImageHeight', im.size[1])
                orientation = exif.get('Orientation', -1)
                make = exif.get('Make', '')
                model = exif.get('Model', '')

                thumbnail = self.generate_thumbnail(filename, im)

                media_id = self.add_media(filename=filename, thumbnail=thumbnail, mimetype=mimetype, timestamp=timestamp, width=width, height=height, orientation=orientation, make=make, model=model)
                media_ids.append(media_id)
            elif 'video' in mimetype:
                try:
                    meta = ffmpeg.probe(filename)
                    format = meta['format']
                    streams = meta['streams']
                    for stream in streams:
                        if stream['codec_type'] == 'video':
                            break
                except:
                    logging.info(f'failed to import {filename}, skipping.')
                    continue

                width = int(stream['width'])
                height = int(stream['height'])
                duration = float(format['duration'])
                timestamp = self.get_video_timestamp(meta)

                thumbnail = self.generate_video_thumbnail(filename, width, height, duration)

                media_id = self.add_media(filename=filename, thumbnail=thumbnail, mimetype=mimetype, timestamp=timestamp, width=width, height=height, orientation=-1, make='', model='')
                media_ids.append(media_id)
            else:
                logging.warning(f'mimetype={mimetype} not recognized as a media format, skipping.')
                continue

        if len(media_ids) == 0:
            return []
        else:
            print(media_ids, tuple(media_ids))
            self.cursor.execute(f'select * from media where id in {tuple(media_ids)} order by timestamp asc')
            return self.cursor.fetchall()

    def add_media(self, filename, thumbnail, mimetype, timestamp='NULL', width=None, height=None, orientation=None, make=None, model=None):
        if timestamp != 'NULL':
            timestamp = f'"{timestamp}"'
        self.cursor.execute(f'insert into media (filename,thumbnail,mimetype,timestamp,width,height,orientation,make,model) values ("{os.path.abspath(filename)}","{thumbnail}","{mimetype}",{timestamp},{width},{height},{orientation},"{make}","{model}")')
        return self.cursor.lastrowid

    def remove_media(self, media_id):
        self.cursor.execute(f'delete from media where id={media_id}')

    def add_album(self, name, password=None):
        if password is not None:
            self.cursor.execute(f'insert into albums (name,password) values ("{name}", SHA2("{password}",256))')
        else:
            self.cursor.execute(f'insert into albums (name) values ("{name}")')
        return self.cursor.lastrowid

    def update_album(self, album_id, **kwargs):
        changes = ','.join([f'{k}="{kwargs[k]}"' if kwargs[k] is not None else f'{k}=NULL' for k in kwargs])
        # password needs a specialized treatment:
        
        if 'password' in kwargs and kwargs['password'] is not None:
            changes = changes.replace(f'"{kwargs["password"]}"', f'SHA2("{kwargs["password"]}",256)')

        self.cursor.execute(f'update albums set {changes} where id={album_id}')

    def add_collection(self, name, password=None):
        if password is not None:
            self.cursor.execute(f'insert into collections (name,password) values ("{name}", SHA2("{password}",256))')
        else:
            self.cursor.execute(f'insert into collections (name) values ("{name}")')
        return self.cursor.lastrowid

    def add_media_to_album(self, media_id, album_id):
        self.cursor.execute(f'insert into media_in_albums (album_id,media_id) values ({album_id},{media_id})')

    def remove_media_from_album(self, media_id, album_id):
        self.cursor.execute(f'delete from media_in_albums where media_id={media_id} and album_id={album_id}')

    def add_album_to_collection(self, album_id, collection_id):
        self.cursor.execute(f'insert into albums_in_collections (collection_id,album_id) values ({collection_id},{album_id})')

    def query_media(self, album_id=None, password=None):
        if album_id is None:
            self.cursor.execute(f'select * from media order by timestamp asc')
            return self.cursor.fetchall()

        if password is None:
            self.cursor.execute(f'select * from media where id in (select media_id from media_in_albums where album_id in (select id from albums where id={album_id} and password is NULL))')
        else:
            self.cursor.execute(f'select * from media where id in (select media_id from media_in_albums where album_id in (select id from albums where id={album_id} and password=sha2("{password}", 256)))')
        return self.cursor.fetchall()

    def set_album_password(self, album_id, password):
        self.cursor.execute(f'update albums set password=sha2("{password}", 256) where id={album_id}')

    def unset_album_password(self, album_id):
        self.cursor.execute(f'update albums set password=NULL where id={album_id}')

    def validate_album_password(self, album_id=None, password=None):
        self.cursor.execute(f'select id from albums where id={album_id} and password=sha2("{password}", 256)')
        res = self.cursor.fetchall()
        if len(res) == 0:
            return False
        return res[0]['id'] == album_id

    def delete_album(self, album_id):
        self.cursor.execute(f'delete from media_in_albums where album_id={album_id}')
        self.cursor.execute(f'delete from albums where id={album_id}')

    def query_albums(self):
        self.cursor.execute(f'select id,name,password is not null as locked from albums order by name asc')
        return self.cursor.fetchall()

    def query_collections(self):
        self.cursor.execute(f'select id,name from collections order by name asc')
        return self.cursor.fetchall()

def import_exif(image, taglist=ExifTags.TAGS):
    tags = dict()
    exif = image.getexif()
    for tag_id in exif:
        tag = taglist.get(tag_id, tag_id)
        val = exif.get(tag_id)
        if type(val) == str:
            val = val.replace('\x00', '').strip()
        tags[tag] = val
    return tags

def init_chromecast():
    # Get local IP:
    if config.CASTER_IP is None:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
    else:
        ip = config.CASTER_IP

    # Initialize local server:
    server = HTTPServer((ip, config.CASTER_PORT), SimpleHTTPRequestHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True

    try:
        thread.start()
        logging.info('built-in casting server started.')
    except:
        server.shutdown()
        raise ValueError('could not start the built-in server')

    # Initialize living room chromecast:
    services, browser = cc.discover_chromecasts()
    cc.stop_discovery(browser)
    chromecasts, browser = cc.get_listed_chromecasts(friendly_names=['Chromecast'])
    cast = chromecasts[0]
    cast.wait()

    return cast.media_controller
