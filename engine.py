"""
"""

import mariadb as mdb
import os
from PIL import Image, ExifTags
import logging

import config

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
        
        self.cursor.execute('create table media (id int unsigned not null auto_increment primary key, filename varchar(256) not null, thumbnail varchar(32) not null, timestamp datetime, width smallint unsigned, height smallint unsigned, orientation tinyint, make varchar(32), model varchar(32))')
        self.cursor.execute('create table collections (id int unsigned not null auto_increment, name varchar(16) not null, primary key(id))')
        self.cursor.execute('create table albums (id int unsigned not null auto_increment, name varchar(100) not null, primary key(id))')
        self.cursor.execute('create table media_in_albums (album_id int unsigned not null, media_id int unsigned not null, foreign key (album_id) references albums(id), foreign key (media_id) references media(id), unique (album_id, media_id))')
        self.cursor.execute('create table albums_in_collections (collection_id int unsigned not null, album_id int unsigned not null, foreign key (collection_id) references collections(id), foreign key (album_id) references albums(id), unique (collection_id, album_id))')

    def media_in_database(self, filename):
        self.cursor.execute(f'select * from media where filename="{filename}"')
        entries = self.cursor.fetchall()
        return False if len(entries) == 0 else True

    def import_media_from_directory(self, path):
        imported_media = []

        files = os.listdir(path)
        for f in files:
            filename = os.path.abspath(path+'/'+f)

            # check if the file is already in the database:
            if self.media_in_database(filename):
                print('skip a duplicate')
                continue

            im = Image.open(filename)
            exif = import_exif(im)

            timestamp = exif.get('DateTimeOriginal', '')
            width = exif.get('ExifImageWidth', -1)
            height = exif.get('ExifImageHeight', -1)
            orientation = exif.get('Orientation', -1)
            make = exif.get('Make', '')
            model = exif.get('Model', '')

            self.add_media(filename, timestamp=timestamp, width=width, height=height, orientation=orientation, make=make, model=model)

            im.thumbnail((256, 256))
            im.save(config.THUMBNAIL_DIR + f'/{f}')
            imported_media.append(config.THUMBNAIL_DIR + f'/{f}')

        return imported_media

    def add_media(self, filename, timestamp='NULL', width=None, height=None, orientation=None, make=None, model=None):
        self.cursor.execute(f'insert into media (filename,thumbnail,timestamp,width,height,orientation,make,model) values ("{os.path.abspath(filename)}","{os.path.basename(filename)}","{timestamp}",{width},{height},{orientation},"{make}","{model}")')

    def query_media(self):
        self.cursor.execute(f'select thumbnail from media order by timestamp asc')
        thumbnail_list = self.cursor.fetchall()
        return [entry['thumbnail'] for entry in thumbnail_list]

    def add_collection(self, name):
        self.cursor.execute(f'insert into collections (name) values ("{name}")')

    def add_album(self, name):
        self.cursor.execute(f'insert into albums (name) values ("{name}")')

    def query_albums(self):
        self.cursor.execute(f'select name from albums order by name asc')
        name_list = self.cursor.fetchall()
        return [entry['name'] for entry in name_list]

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

def import_medium(filename):
    im = Image.open(filename)
    exif = import_exif(im)
    return (im, exif)

def import_media_from_directory(path):
    imported_media = []
    tags = ExifTags.TAGS

    files = os.listdir(path)
    for f in files:
        # try:
        im = Image.open(path+'/'+f)
        exif = import_exif(im)

        im.thumbnail((256, 256))
        im.save(config.THUMBNAIL_DIR + f'/{f}')
        imported_media.append(config.THUMBNAIL_DIR + f'/{f}')

    return imported_media