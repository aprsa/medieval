import config
import os
import mariadb as mdb
import gi
gi.require_version('Gtk', '4.0')

from gi.repository import Gtk as gtk, Gdk as gdk, Gio as gio, GObject as gobject

from PIL import Image

__version__ = '0.1.0'


dbconfig = {
    'host': 'localhost',
    'user': config.MDB_USER,
    'password': config.MDB_PWD,
    'database': config.MDB_DBNAME
}


def create_empty_database(dbc, overwrite=False):
    """
    @overwrite: delete existing database entries (default: False)

    Creates tables in the database. If @overwrite is set to True, it deletes
    any previous database entries.
    """
    if overwrite:
        dbc.execute('drop table if exists media')
        dbc.execute('drop table if exists albums_in_collections')
        dbc.execute('drop table if exists collections')
        dbc.execute('drop table if exists albums')
    
    dbc.execute('create table media (id int unsigned not null auto_increment primary key, filename varchar(16) not null, thumbnail varchar(16) not null)')
    dbc.execute('create table collections (id int unsigned not null auto_increment, name varchar(16) not null, primary key(id))')
    dbc.execute('create table albums (id int unsigned not null auto_increment, name varchar(100) not null, primary key(id))')
    dbc.execute('create table albums_in_collections (collection_id int unsigned not null, album_id int unsigned not null, foreign key (collection_id) references collections(id), foreign key (album_id) references albums(id), unique (collection_id, album_id))')

def add_media(dbc, path):
    dbc.execute(f'insert into media (path) values ({path})')

def add_collection(dbc, name):
    dbc.execute(f'insert into collections (name) values ({name})')

def add_album(dbc, name):
    dbc.execute(f'insert into albums (name) values ({name})')

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

class Album(gtk.Box):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, orientation=gtk.Orientation.HORIZONTAL, **kwargs)
        self.label = gtk.Label(hexpand=False)
        self.append(self.label)
        self.label.set_visible(False)
        self.entry = gtk.Entry()
        self.append(self.entry)
        self.entry.set_visible(True)
        self.entry.connect('activate', self.on_entry_changed)

        dnd = gtk.DropTarget.new(gdk.FileList, gdk.DragAction.COPY)
        dnd.connect('drop', self.on_dnd_drop)
        dnd.connect('accept', self.on_dnd_accept)
        dnd.connect('enter', self.on_dnd_enter)
        dnd.connect('motion', self.on_dnd_motion)
        dnd.connect('leave', self.on_dnd_leave)
        self.add_controller(dnd)

    def on_entry_changed(self, entry):
        name = entry.get_text()
        self.label.set_text(name)
        self.entry.set_visible(False)
        self.label.set_visible(True)

    def on_dnd_drop(self, value, x, y, user_data):
        print(f'in on_dnd_drop(); value={value}, x={x}, y={y}, user_data={user_data}')

    def on_dnd_accept(self, drop, user_data):
        print(f'in on_dnd_accept(); drop={drop}, user_data={user_data}')
        return True

    def on_dnd_enter(self, drop_target, x, y):
        print(f'in on_dnd_enter(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_motion(self, drop_target, x, y):
        print(f'in on_dnd_motion(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_leave(self, user_data):
        print(f'in on_dnd_leave(); user_data={user_data}')

class MediaFile(gtk.FlowBoxChild):
    def __init__(self, *args, file, **kwargs):
        super().__init__(*args, **kwargs)

        self.filename = file

        frame = gtk.Frame()
        self.set_child(frame)

        vbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        frame.set_child(vbox)

        self.image = gtk.Image.new_from_file(file)
        self.image.set_pixel_size(256)
        vbox.append(self.image)

        label = gtk.Label.new(file[file.rfind('/')+1:])
        vbox.append(label)

    def __repr__(self):
        return f'<MediaFile {self.filename}>'

class MediaGallery(gtk.FlowBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.name = kwargs.get('name', 'default')
        self.connect('child-activated', self.on_media_selected)

        dnd = gtk.DragSource.new()
        dnd.set_actions(gdk.DragAction.COPY)
        dnd.connect('prepare', self.on_dnd_prepare)
        dnd.connect('drag-begin', self.on_dnd_begin)
        dnd.connect('drag-end', self.on_dnd_end)
        self.add_controller(dnd)

    def __repr__(self):
        return f'<MediaGallery {self.name}>'

    def on_media_selected(self, gallery, media_file):
        print(f'on_media_selected(); gallery={gallery}, media_file={media_file}')

    def on_dnd_prepare(self, drag_source, x, y):
        data = self.get_selected_children()
        print(f'in on_dnd_prepare(); drag_source={drag_source}, x={x}, y={y}, data={data}')
        if len(data) == 0:
            return None

        paintable = data[0].image.get_paintable()  # TODO: make this nicer for multiple selections
        drag_image = gtk.Image.new_from_paintable(paintable)
        drag_image.set_opacity(0.5)  # FIXME: not sure why transparency doesn't work
        drag_source.set_icon(drag_image.get_paintable(), 128, 128)  # FIXME: not sure why hot_x and hot_y don't work
        
        content = gdk.ContentProvider.new_for_value(data)
        return content

    def on_dnd_begin(self, drag_source, data):
        content = data.get_content()
        print(f'in on_dnd_begin(); drag_source={drag_source}, data={data}, content={content}')

    def on_dnd_end(self, drag, drag_data, some_flag):
        print(f'in on_dnd_end(); drag={drag}, drag_data={drag_data}, some_flag={some_flag}')

class Importer(gtk.FileChooserDialog):
    def __init__(self, parent, select_multiple):
        super().__init__(transient_for=parent, use_header_bar=True)
        self.parent = parent
        self.select_multiple = select_multiple

        self.set_action(action=gtk.FileChooserAction.SELECT_FOLDER)
        title = 'Select directories' if self.select_multiple else 'Select directory'
        self.set_title(title=title)
        self.set_modal(modal=True)
        self.set_select_multiple(select_multiple=self.select_multiple)
        self.connect('response', self.dialog_response)

        self.add_buttons(
            '_Cancel', gtk.ResponseType.CANCEL,
            '_Select', gtk.ResponseType.OK
        )

        self.show()

    def dialog_response(self, widget, response):
        if response == gtk.ResponseType.OK:
            media_list = import_media_from_directory(self.get_file().get_path())
            for f in media_list:
                child = MediaFile(file=f)
                self.parent.gallery.insert(child, -1)

        elif response == gtk.ResponseType.CANCEL:
            print("Cancel clicked")

        widget.close()

class MedievalWindow(gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        app = kwargs.get('application')

        self.album_list = []
        self.collection_list = []

        vbox = gtk.Box(orientation=gtk.Orientation.VERTICAL, spacing=5)
        self.set_child(vbox)

        self.add_action_entries([
            ('file_new', self.on_new_clicked),
            ('file_import', self.on_import_clicked),
        ])

        # action = gio.SimpleAction.new('file_import', None)
        # action.connect('activate', self.on_import_clicked)
        # self.add_action(action)

        menu = gio.Menu.new()

        menu_file = gio.Menu.new()
        file_new = gio.MenuItem.new(label='New', detailed_action='win.file_new')
        file_import = gio.MenuItem.new(label='Import...', detailed_action='win.file_import')
        file_quit = gio.MenuItem.new(label='Quit', detailed_action='app.quit')

        menu_file.append_item(file_new)
        menu_file.append_item(file_import)
        menu_file.append_item(file_quit)
        menu.append_submenu('File', menu_file)

        menubar = gtk.PopoverMenuBar.new_from_model(menu)
        vbox.append(menubar)

        hpanels = gtk.Paned(orientation=gtk.Orientation.HORIZONTAL, position=200)
        vbox.append(hpanels)

        vpanels = gtk.Paned(orientation=gtk.Orientation.VERTICAL)
        hpanels.set_start_child(vpanels)

        collections_frame = gtk.Frame(label='Collections', vexpand=True)
        vpanels.set_start_child(collections_frame)

        cbbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        collections_frame.set_child(cbbox)

        self.collections = gtk.ListBox(activate_on_single_click=True, selection_mode=gtk.SelectionMode.BROWSE, show_separators=True, vexpand=True)
        cbbox.append(self.collections)

        new_collection_button = gtk.Button.new_with_label('Add Collection...')
        cbbox.append(new_collection_button)

        albums_frame = gtk.Frame(label='Albums')
        vpanels.set_end_child(albums_frame)

        abbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        albums_frame.set_child(abbox)

        self.albums = gtk.ListBox(activate_on_single_click=True, selection_mode=gtk.SelectionMode.BROWSE, show_separators=True, vexpand=True)
        abbox.append(self.albums)

        new_album_button = gtk.Button.new_with_label('Add Album...')
        new_album_button.connect('clicked', self.on_new_album_clicked)
        abbox.append(new_album_button)

        display_frame = gtk.Frame(label='Gallery', vexpand=True)
        hpanels.set_end_child(display_frame)

        scrolled_panel = gtk.ScrolledWindow(hscrollbar_policy=gtk.PolicyType.NEVER, vscrollbar_policy=gtk.PolicyType.AUTOMATIC)
        display_frame.set_child(scrolled_panel)

        self.gallery = MediaGallery(homogeneous=True, column_spacing=5, row_spacing=5, valign=gtk.Align.START, halign=gtk.Align.FILL, activate_on_single_click=False, selection_mode=gtk.SelectionMode.MULTIPLE)
        scrolled_panel.set_child(self.gallery)

        button = gtk.Button(label='Quit')
        button.connect('clicked', lambda _: app.quit())
        vbox.append(button)
        self.set_title(kwargs.get('title'))

    def on_new_album_clicked(self, user_data):
        album = Album()
        self.album_list.append(album)
        self.albums.append(album)
        row = self.albums.get_row_at_index(len(self.album_list)-1)
        self.albums.drag_highlight_row(row)
        album.entry.grab_focus()

    def on_menu(self, simple_action, parameter):
        print(f'simple_action: {simple_action}, parameter: {parameter}')

    def on_new_clicked(self, action, parameter, app):
        print(f'new(); action={action}, parameter={parameter}, app={app}')

    def on_import_clicked(self, action, parameter, app):
        Importer(self, False)

class MedievalApp(gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id='org.medieval.Medieval', flags=gio.ApplicationFlags.FLAGS_NONE, **kwargs)

    def do_startup(self):
        print('in do_startup()')
        gtk.Application.do_startup(self)

        if not os.path.exists(config.THUMBNAIL_DIR):
            os.makedirs(config.THUMBNAIL_DIR, mode=0o755, exist_ok=True)
        
        try:
            self.db = mdb.connect(**dbconfig)
            self.dbc = self.db.cursor(dictionary=True) # for mariadb module
            self.db.autocommit = True
        except mdb.Error as e:
            print(f'error connecting to the database: {e}')
            exit(1)

        action = gio.SimpleAction.new('quit', None)
        action.connect('activate', self.on_quit)
        self.add_action(action)

    def do_activate(self):
        print('in do_activate()')
        main = self.props.active_window
        if not main:
            main = MedievalWindow(title='Medieval -- Media Organizer', application=self, default_width=1600, default_height=800)
        main.present()

    def do_open(self):
        print('in do_open()')

    def do_shutdown(self):
        print('in do_shutdown()')
        gtk.Application.do_shutdown(self)

    def on_quit(self, action, param):
        self.quit()

if __name__ == '__main__':
    medieval = MedievalApp()
    medieval.run()