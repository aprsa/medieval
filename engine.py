"""
"""

import mariadb as mdb
import os
from PIL import Image
import logging

import config

__version__ = '0.1.0'

dbconfig = {
    'host': 'localhost',
    'user': config.MDB_USER,
    'password': config.MDB_PWD,
    'database': config.MDB_DBNAME
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
            self.cursor.execute('drop table if exists media')
            self.cursor.execute('drop table if exists albums_in_collections')
            self.cursor.execute('drop table if exists media_in_albums')
            self.cursor.execute('drop table if exists collections')
            self.cursor.execute('drop table if exists albums')
        
        self.cursor.execute('create table media (id int unsigned not null auto_increment primary key, filename varchar(16) not null, thumbnail varchar(16) not null)')
        self.cursor.execute('create table collections (id int unsigned not null auto_increment, name varchar(16) not null, primary key(id))')
        self.cursor.execute('create table albums (id int unsigned not null auto_increment, name varchar(100) not null, primary key(id))')
        self.cursor.execute('create table media_in_albums (album_id int unsigned not null, media_id int unsigned not null, foreign key (album_id) references albums(id), foreign key (media_id) references media(id), unique (album_id, media_id))')
        self.cursor.execute('create table albums_in_collections (collection_id int unsigned not null, album_id int unsigned not null, foreign key (collection_id) references collections(id), foreign key (album_id) references albums(id), unique (collection_id, album_id))')

    def add_media(self, dbc, path):
        self.cursor.execute(f'insert into media (path) values ({path})')

    def add_collection(self, name):
        self.cursor.execute(f'insert into collections (name) values ({name})')

    def add_album(self, name):
        self.cursor.execute(f'insert into albums (name) values ({name})')

def import_media_from_directory(path):
    imported_media = []

    files = os.listdir(path)
    for f in files:
        # try:
        im = Image.open(path+'/'+f)
        im.thumbnail((256, 256))
        im.save(config.THUMBNAIL_DIR + f'/{f}')
        imported_media.append(config.THUMBNAIL_DIR + f'/{f}')

    return imported_media
