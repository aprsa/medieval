import os
import logging

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk as gtk, Gdk as gdk, Gio as gio, GObject as gobject, GLib as glib

from PIL import Image, ImageFilter

import config
import engine


class Collection(gtk.Box):
    def __init__(self, *args, **kwargs):
        super().__init__(orientation=gtk.Orientation.HORIZONTAL)

        name = kwargs.get('name', None)
        self.collection_id = kwargs.get('collection_id', None)

        self.label = gtk.Label(hexpand=False)
        self.append(self.label)
        self.entry = gtk.Entry()
        self.append(self.entry)
        self.entry.connect('activate', self.on_entry_changed)

        if name is None:
            self.label.set_visible(False)
            self.entry.set_visible(True)
        else:
            self.label.set_text(name)
            self.label.set_visible(True)
            self.entry.set_visible(False)

        dnd_a2c = gtk.DropTarget.new(gio.ListModel, gdk.DragAction.COPY)
        dnd_a2c.connect('drop', self.on_dnd_drop)
        dnd_a2c.connect('accept', self.on_dnd_accept)
        dnd_a2c.connect('enter', self.on_dnd_enter)
        dnd_a2c.connect('motion', self.on_dnd_motion)
        dnd_a2c.connect('leave', self.on_dnd_leave)
        self.add_controller(dnd_a2c)

    def on_entry_changed(self, entry):
        name = entry.get_text()
        self.collection_id = medieval.engine.add_collection(name=name)
        self.label.set_text(name)
        self.entry.set_visible(False)
        self.label.set_visible(True)

    def on_dnd_drop(self, drop_target, value, x, y):
        logging.info(f'in on_dnd_drop(); drop_target={drop_target}, value={value}, x={x}, y={y}')
        for entry in list(value):
            medieval.engine.add_album_to_collection(album_id=entry.album_id, collection_id=self.collection_id)

    def on_dnd_accept(self, drop_target, drop):
        logging.info(f'in on_dnd_accept(); drop_target={drop_target}, drop={drop}')
        return True

    def on_dnd_enter(self, drop_target, x, y):
        logging.info(f'in on_dnd_enter(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_motion(self, drop_target, x, y):
        logging.info(f'in on_dnd_motion(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_leave(self, user_data):
        logging.info(f'in on_dnd_leave(); user_data={user_data}')

class Album(gtk.Box):
    def __init__(self, *args, **kwargs):
        super().__init__(orientation=gtk.Orientation.HORIZONTAL)

        self.name = kwargs.get('name', None)
        self.album_id = kwargs.get('album_id', None)

        self.label = gtk.EditableLabel(hexpand=False)
        self.label.connect('notify', self.on_album_edited)
        self.append(self.label)

        if self.name is not None:
            self.label.set_text(self.name)
            self.label.set_editable(False)

        # Controller for dragging media to albums:
        dnd_m2a = gtk.DropTarget.new(gio.ListModel, gdk.DragAction.COPY)
        dnd_m2a.connect('drop', self.on_dnd_drop)
        dnd_m2a.connect('accept', self.on_dnd_accept)
        dnd_m2a.connect('enter', self.on_dnd_enter)
        dnd_m2a.connect('motion', self.on_dnd_motion)
        dnd_m2a.connect('leave', self.on_dnd_leave)
        self.add_controller(dnd_m2a)

        # Controller for dragging albums to collections:
        dnd_a2c = gtk.DragSource.new()
        dnd_a2c.set_actions(gdk.DragAction.COPY)
        dnd_a2c.connect('prepare', self.on_dnd_prepare)
        dnd_a2c.connect('drag-begin', self.on_dnd_begin)
        dnd_a2c.connect('drag-end', self.on_dnd_end)
        self.add_controller(dnd_a2c)

        # Right-click gesture:
        gesture = gtk.GestureClick.new()
        gesture.set_button(3)
        gesture.connect('pressed', self.on_album_rightclicked)
        self.add_controller(gesture)

        # Define actions and pack them into a dedicated group:
        action_group = gio.SimpleActionGroup.new()

        album_rename = gio.SimpleAction.new('rename', None)
        album_rename.connect('activate', self.on_album_rename)

        album_delete = gio.SimpleAction.new('delete', None)
        album_delete.connect('activate', self.on_album_delete)

        action_group.add_action(album_rename)
        action_group.add_action(album_delete)

        self.insert_action_group('album', action_group)

    def __repr__(self):
        return f'<Album {self.name}, id={self.album_id}>'

    def on_album_edited(self, label, data):
        if data.name != 'editing':
            # we don't care about any notification other than 'editing'.
            return
        
        if label.get_property('editing') is True:
            # editing still in progress, nothing to be done yet.
            return
        
        logging.info(f'on_album_edited(): self={self}, label={label}, new_label={label.get_property("text")}')
        label.set_editable(False)

        if self.name is None:
            # Album is being added for the first time.
            self.name = label.get_property('text')
            self.album_id = medieval.engine.add_album(name=self.name)
        else:
            # Album is being renamed.
            self.name = label.get_property('text')
            medieval.engine.update_album(album_id=self.album_id, name=self.name)

    def on_album_rightclicked(self, click, n_press, x, y):
        print(f'on_album_rightclicked(): self={self}, click={click}, n_press={n_press}, x={x}, y={y}')

        context_menu = gio.Menu.new()
        rename = gio.MenuItem.new(label='Rename', detailed_action='album.rename')
        delete = gio.MenuItem.new(label='Delete', detailed_action='album.delete')

        context_menu.append_item(rename)
        context_menu.append_item(delete)

        menu = gtk.PopoverMenu.new_from_model(context_menu)
        menu.set_parent(self)
        menu.popup()

    def on_album_rename(self, action, data):
        logging.info(f'on_album_rename(). self={self}, action={action}, data={data}')
        self.label.set_editable(True)
        self.label.start_editing()

    def on_album_delete(self, action, data):
        logging.info(f'on_album_delete(). self={self}, action={action}, data={data}')
        medieval.engine.delete_album(album_id=self.album_id)
        medieval.main_window.albums.remove(self.get_parent())

    def on_dnd_prepare(self, drag_source, x, y):
        album = gio.ListStore()
        album.append(self)
        logging.info(f'in on_dnd_prepare(); drag_source={drag_source}, x={x}, y={y}, data={album}')

        passed_data = gobject.Value(gio.ListModel, album)
        content = gdk.ContentProvider.new_for_value(passed_data)

        # thumbnails = [Image.open(entry.filename) for entry in self.gallery.get_selected_children()]
        # self.create_drag_icon(thumbnails)
        # drag_image = gtk.Image.new_from_file(config.THUMBNAIL_DIR+'/drag_icon.png')

        # paintable = media[0].image.get_paintable()  # TODO: make this nicer for multiple selections
        # drag_image = gtk.Image.new_from_paintable(paintable)
        # drag_source.set_icon(drag_image.get_paintable(), 128, 128)  # TODO: consider a better hot_x, hot_y default
        
        return content

    def on_dnd_begin(self, drag_source, data):
        content = data.get_content()
        logging.info(f'in on_dnd_begin(); drag_source={drag_source}, data={data}, content={content}')

    def on_dnd_end(self, drag, drag_data, some_flag):
        logging.info(f'in on_dnd_end(); drag={drag}, drag_data={drag_data}, some_flag={some_flag}')

    def on_dnd_drop(self, drop_target, value, x, y):
        logging.info(f'in on_dnd_drop(); drop_target={drop_target}, value={value}, x={x}, y={y}')
        for entry in list(value):
            medieval.engine.add_media_to_album(media_id=entry.media_id, album_id=self.album_id)

    def on_dnd_accept(self, drop_target, drop):
        logging.info(f'in on_dnd_accept(); drop_target={drop_target}, drop={drop}')
        return True

    def on_dnd_enter(self, drop_target, x, y):
        logging.info(f'in on_dnd_enter(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_motion(self, drop_target, x, y):
        logging.info(f'in on_dnd_motion(); drop_target={drop_target}, x={x}, y={y}')
        return gdk.DragAction.COPY

    def on_dnd_leave(self, user_data):
        logging.info(f'in on_dnd_leave(); user_data={user_data}')

class Tag(gtk.Box):
    def __init__(self, *args, **kwargs):
        super().__init__(orientation=gtk.Orientation.HORIZONTAL)

        name = kwargs.get('name', None)
        self.tag_id = kwargs.get('tag_id', None)

        self.label = gtk.Label(hexpand=False)
        self.append(self.label)
        self.entry = gtk.Entry()
        self.append(self.entry)
        self.entry.connect('activate', self.on_entry_changed)

        if name is None:
            self.label.set_visible(False)
            self.entry.set_visible(True)
        else:
            self.label.set_text(name)
            self.label.set_visible(True)
            self.entry.set_visible(False)

        # dnd_a2c = gtk.DropTarget.new(gio.ListModel, gdk.DragAction.COPY)
        # dnd_a2c.connect('drop', self.on_dnd_drop)
        # dnd_a2c.connect('accept', self.on_dnd_accept)
        # dnd_a2c.connect('enter', self.on_dnd_enter)
        # dnd_a2c.connect('motion', self.on_dnd_motion)
        # dnd_a2c.connect('leave', self.on_dnd_leave)
        # self.add_controller(dnd_a2c)

    def on_entry_changed(self, entry):
        name = entry.get_text()
        self.tag_id = medieval.engine.add_tag(name=name)
        self.label.set_text(name)
        self.entry.set_visible(False)
        self.label.set_visible(True)

    # def on_dnd_drop(self, drop_target, value, x, y):
    #     logging.info(f'in on_dnd_drop(); drop_target={drop_target}, value={value}, x={x}, y={y}')
    #     for entry in list(value):
    #         medieval.engine.add_album_to_collection(album_id=entry.album_id, collection_id=self.collection_id)

    # def on_dnd_accept(self, drop_target, drop):
    #     logging.info(f'in on_dnd_accept(); drop_target={drop_target}, drop={drop}')
    #     return True

    # def on_dnd_enter(self, drop_target, x, y):
    #     logging.info(f'in on_dnd_enter(); drop_target={drop_target}, x={x}, y={y}')
    #     return gdk.DragAction.COPY

    # def on_dnd_motion(self, drop_target, x, y):
    #     logging.info(f'in on_dnd_motion(); drop_target={drop_target}, x={x}, y={y}')
    #     return gdk.DragAction.COPY

    # def on_dnd_leave(self, user_data):
    #     logging.info(f'in on_dnd_leave(); user_data={user_data}')

class MediaFile(gtk.FlowBoxChild):
    def __init__(self, *args, **kwargs):
        super().__init__()

        self.filename = kwargs.get('filename', None)
        self.thumbnail = kwargs.get('thumbnail', None)
        self.media_id = kwargs.get('media_id', None)
        self.timestamp = kwargs.get('timestamp', None)

        frame = gtk.Frame()
        self.set_child(frame)

        vbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        frame.set_child(vbox)

        self.image = gtk.Image.new_from_file(self.thumbnail)
        self.image.set_pixel_size(256)
        vbox.append(self.image)

        label = gtk.Label.new(self.filename[self.filename.rfind('/')+1:])
        vbox.append(label)

    def __repr__(self):
        return f'<MediaFile {self.filename}>'

    def basename(self):
        return os.path.basename(self.filename)

class DisplayPanel(gtk.Paned):
    def __init__(self, *args, **kwargs):
        super().__init__(orientation=gtk.Orientation.HORIZONTAL)

        gallery_panel = gtk.Box(orientation=gtk.Orientation.HORIZONTAL)
        self.set_start_child(gallery_panel)

        # timeline frame (visible by default):
        self.timeline = gtk.FlowBox(homogeneous=True, column_spacing=5, row_spacing=5, valign=gtk.Align.START, halign=gtk.Align.FILL, activate_on_single_click=False, selection_mode=gtk.SelectionMode.MULTIPLE)
        self.timeline.connect('child-activated', self.on_media_selected)
        
        scrolled_panel = gtk.ScrolledWindow(hscrollbar_policy=gtk.PolicyType.NEVER, vscrollbar_policy=gtk.PolicyType.AUTOMATIC, hexpand=True, vexpand=True)
        scrolled_panel.set_child(self.timeline)
                
        self.timeline_frame = gtk.Frame(label='Timeline', hexpand=True, vexpand=True)
        self.timeline_frame.set_child(scrolled_panel)
        gallery_panel.append(self.timeline_frame)

        # gallery (album) frame (invisible by default):
        self.gallery = gtk.FlowBox(homogeneous=True, column_spacing=5, row_spacing=5, valign=gtk.Align.START, halign=gtk.Align.FILL, activate_on_single_click=False, selection_mode=gtk.SelectionMode.MULTIPLE)
        self.gallery.connect('child-activated', self.on_media_selected)
        scrolled_panel = gtk.ScrolledWindow(hscrollbar_policy=gtk.PolicyType.NEVER, vscrollbar_policy=gtk.PolicyType.AUTOMATIC, hexpand=True, vexpand=True)
        scrolled_panel.set_child(self.gallery)

        gallery_frame = gtk.Frame(label='Album', hexpand=True, vexpand=True)
        gallery_frame.set_child(scrolled_panel)
        # gallery_panel.append(self.gallery_frame)

        self.gallery_frame = gtk.Overlay()
        self.gallery_frame.set_child(gallery_frame)
        gallery_panel.append(self.gallery_frame)
        self.gallery_frame.set_visible(False)

        close_button = gtk.Button.new_from_icon_name('window-close')
        close_button.set_halign(gtk.Align.END)
        close_button.set_valign(gtk.Align.START)
        close_button.connect('clicked', self.on_album_closed)
        self.gallery_frame.add_overlay(close_button)

        # picture area (invisible by default):
        self.picture_area = gtk.ScrolledWindow(hscrollbar_policy=gtk.PolicyType.AUTOMATIC, vscrollbar_policy=gtk.PolicyType.AUTOMATIC)
        gesture = gtk.GestureClick.new()
        gesture.connect('pressed', self.on_picture_clicked)
        self.picture_area.add_controller(gesture)

        picture_frame = gtk.Frame(label='Image', hexpand=True, vexpand=True)
        self.picture_frame = gtk.Overlay()
        self.picture_frame.set_child(picture_frame)
        self.picture_frame.set_visible(False)
        
        close_button = gtk.Button.new_from_icon_name('window-close')
        close_button.set_halign(gtk.Align.END)
        close_button.set_valign(gtk.Align.START)
        close_button.connect('clicked', self.on_picture_frame_closed)
        self.picture_frame.add_overlay(close_button)
        
        picture_frame.set_child(self.picture_area)
        self.set_end_child(self.picture_frame)

        keypress = gtk.EventControllerKey.new()
        keypress.connect('key-pressed', self.on_keypress)
        self.picture_area.add_controller(keypress)

        self.name = kwargs.get('name', 'default')

        dnd = gtk.DragSource.new()
        dnd.set_actions(gdk.DragAction.COPY)
        dnd.connect('prepare', self.on_dnd_prepare)
        dnd.connect('drag-begin', self.on_dnd_begin)
        dnd.connect('drag-end', self.on_dnd_end)
        self.timeline.add_controller(dnd)

        # keep a tab on what's visible so that we can revert when necessary:
        self.picture_state = False
        self.timeline_state = None
        self.gallery_state = None

        # Precompute portrait and landscape drop shadows:
        self.drop_shadows = {}
        self.drop_shadows['256x192'] = self.drop_shadow(size=(256, 192), iterations=10, border=8, offset=(0, 0))
        self.drop_shadows['192x256'] = self.drop_shadow(size=(192, 256), iterations=10, border=8, offset=(0, 0))

    def __repr__(self):
        return f'<DisplayPanel {self.name}>'

    def drop_shadow(self, size, iterations, border, offset, background_color=(0, 0, 0, 1)):
        shadow = self.drop_shadows.get(f'{size[0]}x{size[1]}', None)
        if shadow:
            return shadow

        # calculate the size of the shadow image
        full_width  = size[0] + abs(offset[0]) + 2*border
        full_height = size[1] + abs(offset[1]) + 2*border
        
        shadow = Image.new('RGBA', (full_width, full_height), background_color)
        
        shadow_left = border + max(offset[0], 0)
        shadow_top  = border + max(offset[1], 0)

        shadow.paste('black', [shadow_left, shadow_top, shadow_left + size[0], shadow_top  + size[1]])
        
        for i in range(iterations):
            shadow = shadow.filter(ImageFilter.BLUR)

        return shadow

    def create_drag_icon(self, media):
        # Set width and height as the largest thumbnail width/height capped at 256.
        # Capping is un-necessary because thumbnails are already capped to 256, but
        # it doesn't really hurt.
        width = min(max([medium.width for medium in media]), 256)
        height = min(max([medium.height for medium in media]), 256)
        
        # The final width and height need to accommodate for shadow size as well.
        composite = Image.new(mode='RGBA', size=(width+16*min(len(media), 2), height+16*min(len(media), 2)), color=(0, 0, 0, 1))

        # shadows = [self.drop_shadow(media[0].getbbox()[2:], 10, 8, (0, 0)), self.drop_shadow((width, height), 10, 8, (0, 0)), self.drop_shadow(media[-1].getbbox()[2:], 10, 8, (0, 0))]

        if len(media) == 1:
            shadow = self.drop_shadow(media[0].getbbox()[2:], 10, 8, (0, 0))
            composite.paste(shadow, (0, 0, shadow.width, shadow.height))
            composite.paste(media[0], (8, 8, 8+media[0].width, 8+media[0].height))
        elif len(media) == 2:
            shadow1 = self.drop_shadow(media[1].getbbox()[2:], 10, 8, (0, 0))
            shadow2 = self.drop_shadow(media[0].getbbox()[2:], 10, 8, (0, 0))
            composite.paste(shadow1, (16, 16, 16+shadow1.width, 16+shadow1.height))
            composite.paste(media[1], (24, 24, 24+media[1].width, 24+media[1].height))
            composite.alpha_composite(shadow2, (0, 0))
            composite.paste(media[0], (8, 8, 8+media[0].width, 8+media[0].height))
        elif len(media) == 3:
            shadow1 = self.drop_shadow(media[2].getbbox()[2:], 10, 8, (0, 0))
            shadow2 = self.drop_shadow(media[0].getbbox()[2:], 10, 8, (0, 0))
            composite.paste(shadow1, (16, 16, 16+shadow1.width, 16+shadow1.height))
            composite.paste(media[1], (24, 24, 24+media[1].width, 24+media[1].height))
            composite.alpha_composite(shadow2, (8, 8))
            composite.paste('grey', (16, 16, 16+media[1].width, 16+media[1].height))
            composite.alpha_composite(shadow2, (0, 0))
            composite.paste(media[0], (8, 8, 8+media[0].width, 8+media[0].height))
        else:
            shadow1 = self.drop_shadow(media[-1].getbbox()[2:], 10, 8, (0, 0))
            shadow2 = self.drop_shadow(media[0].getbbox()[2:], 10, 8, (0, 0))
            composite.paste(shadow1, (16, 16, 16+shadow1.width, 16+shadow1.height))
            composite.paste(media[-1], (24, 24, 24+media[1].width, 24+media[1].height))
            composite.alpha_composite(shadow2, (10, 10))
            composite.paste('grey', (18, 18, 18+media[1].width, 18+media[1].height))
            composite.alpha_composite(shadow2, (6, 6))
            composite.paste('grey', (14, 14, 14+media[1].width, 14+media[1].height))
            composite.alpha_composite(shadow2, (0, 0))
            composite.paste(media[0], (8, 8, 8+media[0].width, 8+media[0].height))
        # for i in range(thno):
            # thumbnails[i].putalpha(alpha[i])
            # im.alpha_composite(thumbnails[i], (16*i, 16*i))
            # im.paste(thumbnails[i], box=())

        # buffer = glib.Bytes.new(composite.tobytes())
        # pixbuf = gdk.Pixbuf.new_from_data(buffer.get_data(), gdk.Pixbuf.Colorspace)
        composite.save(config.THUMBNAIL_DIR+'/drag_icon.png')
        return composite

    def on_media_selected(self, gallery, media_file):
        logging.info(f'on_media_selected(); gallery={gallery}, media_file={media_file}')
        picture = gtk.Picture.new_for_filename(media_file.filename)
        picture.set_can_shrink(True)
        self.picture_frame.get_child().set_label(media_file.basename())
        self.picture_area.set_child(picture)
        self.picture_area.grab_focus()
        self.picture_frame.set_visible(True)

    def on_album_closed(self, button):
        logging.info(f'on_album_closed(): self={self}, button={button}')
        self.gallery_frame.set_visible(False)
        self.timeline_frame.set_visible(True)
        medieval.main_window.albums.select_row(None)

    def on_picture_frame_closed(self, button):
        logging.info(f'on_picture_frame_closed(): self={self}, button={button}')
        self.picture_frame.set_visible(False)
        # self.timeline_frame.set_visible(self.timeline_state)
        # self.gallery_frame.set_visible(self.gallery_state)

    def on_dnd_prepare(self, drag_source, x, y):
        media = gio.ListStore()
        media.splice(0, 0, self.timeline.get_selected_children())
        num_items = media.get_n_items()
        logging.info(f'in on_dnd_prepare(); drag_source={drag_source}, x={x}, y={y}, data={media}, num_items={num_items}')
        if num_items == 0:
            return None

        passed_data = gobject.Value(gio.ListModel, media)
        content = gdk.ContentProvider.new_for_value(passed_data)

        thumbnails = [Image.open(entry.thumbnail) for entry in self.timeline.get_selected_children()]
        self.create_drag_icon(thumbnails)
        drag_image = gtk.Image.new_from_file(config.THUMBNAIL_DIR+'/drag_icon.png')

        # paintable = media[0].image.get_paintable()  # TODO: make this nicer for multiple selections
        # drag_image = gtk.Image.new_from_paintable(paintable)
        drag_source.set_icon(drag_image.get_paintable(), 128, 128)  # TODO: consider a better hot_x, hot_y default
        
        return content

    def on_dnd_begin(self, drag_source, data):
        content = data.get_content()
        logging.info(f'in on_dnd_begin(); drag_source={drag_source}, data={data}, content={content}')

    def on_dnd_end(self, drag, drag_data, some_flag):
        logging.info(f'in on_dnd_end(); drag={drag}, drag_data={drag_data}, some_flag={some_flag}')

    def on_keypress(self, controller, keyval, keycode, state):
        logging.info(f'controller={controller}, keyval={keyval}, keycode={keycode}, state={state}')
        if keycode == 9:  # ESC key
            self.picture_frame.set_visible(False)
            self.gallery_frame.set_visible(True)
            return True
        return False

    def on_picture_clicked(self, click, n_press, x, y):
        logging.info(f'on_picture_clicked(): click={click}, n_press={n_press}, x={x}, y={y}')
        if n_press == 2:
            # self.picture_frame.set_visible(False)
            if self.picture_state == False:
                self.gallery_state = self.gallery_frame.get_visible()
                self.timeline_state = self.timeline_frame.get_visible()
                self.gallery_frame.set_visible(False)
                self.timeline_frame.set_visible(False)
                self.picture_state = True
            else:
                self.timeline_frame.set_visible(self.timeline_state)
                self.gallery_frame.set_visible(self.gallery_state)
                self.picture_state = False

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
            media_list = medieval.engine.import_media_from_directory(self.get_file().get_path())
            for entry in media_list:
                child = MediaFile(filename=entry['filename'], thumbnail=f'{config.THUMBNAIL_DIR}/{entry["thumbnail"]}.jpg', media_id=entry['id'], timestamp=entry['timestamp'])
                self.parent.display.timeline.insert(child, -1)

        elif response == gtk.ResponseType.CANCEL:
            logging.info("Cancel clicked")

        widget.close()

class MedievalWindow(gtk.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        app = kwargs.get('application')

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
        self.collections.connect('row_activated', self.on_collection_selected)
        cbbox.append(self.collections)

        new_collection_button = gtk.Button.new_with_label('Add Collection...')
        new_collection_button.connect('clicked', self.on_new_collection_clicked)
        cbbox.append(new_collection_button)

        albums_frame = gtk.Frame(label='Albums')
        vpanels.set_end_child(albums_frame)

        abbox = gtk.Box(orientation=gtk.Orientation.VERTICAL)
        albums_frame.set_child(abbox)

        self.albums = gtk.ListBox(activate_on_single_click=True, selection_mode=gtk.SelectionMode.BROWSE, show_separators=True, vexpand=True)
        self.albums.connect('row_activated', self.on_album_selected)
        abbox.append(self.albums)

        new_album_button = gtk.Button.new_with_label('Add Album...')
        new_album_button.connect('clicked', self.on_new_album_clicked)
        abbox.append(new_album_button)

        self.display = DisplayPanel(name='Gallery')
        hpanels.set_end_child(self.display)

        button = gtk.Button(label='Quit')
        button.connect('clicked', lambda _: app.quit())
        vbox.append(button)
        self.set_title(kwargs.get('title'))

    def on_new_collection_clicked(self, button):
        print(f'on_new_collection_clicked(), button={button}')
        collection = Collection()
        self.collections.append(collection)
        collection.entry.grab_focus()

    def on_collection_selected(self, listbox, row):
        print(f'on_collection_selected(), listbox={listbox}, row={row}, collection_id={row.get_child().collection_id}')

    def on_new_album_clicked(self, button):
        print(f'on_new_album_clicked(), button={button}')
        album = Album()
        self.albums.append(album)
        album.label.start_editing()

    def on_album_selected(self, listbox, row):
        logging.info(f'on_album_selected(), listbox={listbox}, row={row}, album_id={row.get_child().album_id}')

        # remove old media:
        self.display.gallery.select_all()
        for child in self.display.gallery.get_selected_children():
            self.display.gallery.remove(child)

        # populate gallery with new media:
        media = medieval.engine.query_media(album_id=row.get_child().album_id)
        for entry in media:
            child = MediaFile(filename=entry['filename'], thumbnail=f'{config.THUMBNAIL_DIR}/{entry["thumbnail"]}.jpg', media_id=entry['id'], timestamp=entry['timestamp'])
            self.display.gallery.insert(child, -1)

        self.display.timeline_frame.set_visible(False)
        self.display.gallery_frame.set_visible(True)

    def on_menu(self, simple_action, parameter):
        logging.info(f'simple_action: {simple_action}, parameter: {parameter}')

    def on_new_clicked(self, action, parameter, app):
        logging.info(f'on_new_clicked(); action={action}, parameter={parameter}, app={app}')

    def on_import_clicked(self, action, parameter, app):
        Importer(self, False)

class MedievalApp(gtk.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, application_id='org.medieval.Medieval', flags=gio.ApplicationFlags.FLAGS_NONE, **kwargs)

    def do_startup(self):
        logging.info('in do_startup()')
        gtk.Application.do_startup(self)

        self.engine = engine.MedievalDB()
        
        action = gio.SimpleAction.new('quit', None)
        action.connect('activate', self.on_quit)
        self.add_action(action)

    def do_activate(self):
        logging.info('in do_activate()')
        self.main_window = self.props.active_window
        if not self.main_window:
            self.main_window = MedievalWindow(title='Medieval -- Media Organizer', application=self, default_width=1600, default_height=800)

            # Populate the timeline with thumbnails:
            media_list = self.engine.query_media()
            for entry in media_list:
                child = MediaFile(filename=entry['filename'], thumbnail=f'{config.THUMBNAIL_DIR}/{entry["thumbnail"]}.jpg', media_id=entry['id'], timestamp=entry['timestamp'])
                self.main_window.display.timeline.insert(child, -1)

            # Populate collections:
            collection_list = self.engine.query_collections()
            for entry in collection_list:
                collection = Collection(name=entry['name'], collection_id=entry['id'])
                self.main_window.collections.append(collection)

            # Populate albums:
            album_list = self.engine.query_albums()
            for entry in album_list:
                album = Album(name=entry['name'], album_id=entry['id'])
                self.main_window.albums.append(album)

        self.main_window.present()

    def do_open(self):
        logging.info('in do_open()')

    def do_shutdown(self):
        logging.info('in do_shutdown()')
        gtk.Application.do_shutdown(self)

    def on_quit(self, action, param):
        self.quit()

if __name__ == '__main__':
    logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.INFO, handlers=[logging.StreamHandler(),]) #, logging.FileHandler('broker.log')])
    # logger = logging.Logger(name='medieval', clevel='INFO')
    medieval = MedievalApp()
    medieval.run()