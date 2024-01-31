import os
from cudatext import *
from cudatext_keys import *

MAX_RESULTS_LINES = 100
MAX_FILE_SIZE_MB = 5
DO_NOT_SEARCH = ['.git', '.cudatext', '__pycache__', '__trash']

IS_WIN = os.name == 'nt'
BOM = b'\xef\xbb\xbf'

def trim_start(string, substring):
    return string[len(substring):] if string.startswith(substring) else string
    
def is_hidden(path):
    if IS_WIN:
        return os.stat(path).st_file_attributes & 2 != 0
    return os.path.basename(path).startswith('.')

class Command:
    def __init__(self):
        self.input: Editor = None
        self.path:  Editor = None
        self.memo:  Editor = None
        self.h_dlg = None
        self.search_results = {}
        self.in_process = False
        self.terminate_search = False
    
    def status(self, text):
        dlg_proc(self.h_dlg, DLG_CTL_PROP_SET, name='status', prop={'cap': text})
    
    def goto_file(self):
        if self.search_results:
            try:
                file_path, line = self.search_results[self.memo.get_carets()[0][1]]
                file_open(file_path)
                ed.set_caret(0, line)
                dlg_proc(self.h_dlg, DLG_FOCUS)
            except KeyError:
                pass
        
    def on_dlg_close(self, id_dlg, id_ctl, data='', info=''):
        self.search_results.clear()
        if self.in_process:
            self.terminate_search = True
        
    def on_click_dbl(self, id_dlg, id_ctl, data='', info=''):
        self.goto_file()
    
    def on_dlg_key_down(self, id_dlg, id_ctl, data='', info=''):
        key = id_ctl
        if key not in (VK_TAB, VK_ENTER):
            return

        if key == VK_TAB:
            if self.memo.get_prop(PROP_FOCUSED):
                self.input.focus()
                #focused_ctl = 'input' if self.memo.get_prop(PROP_FOCUSED) else 'memo'
                
                #dlg_proc(self.h_dlg, DLG_CTL_FOCUS, name=focused_ctl)
                
                return False
        elif key == VK_ENTER:
            if not self.memo.get_prop(PROP_FOCUSED):
                string = self.input.get_text_all().strip()
                path = self.path.get_text_all().strip()
                if string and path:
                    self.search(string, path)
                else:
                    self.status('Please enter something')
                    self.terminate_search = True
            else:
                self.goto_file()
            return False
    
    def search(self, string, path):
        # terminate ongoing search if any
        if self.in_process:
            # terminate current search and schedule new one
            self.terminate_search = True
            timer_proc(TIMER_START_ONE, lambda *args, **kwargs: self.search(string, path), 50)
            return
        
        self.in_process = True
        
        self.memo.set_prop(PROP_RO, False)
        self.memo.set_prop(PROP_LEXER_FILE, ed.get_prop(PROP_LEXER_FILE))
        #self.memo.set_prop(PROP_LEXER_FILE, 'Search results')
        self.memo.set_text_all('')
        self.memo.focus()
        self.search_results.clear()
        path = os.path.expanduser(path) # expand '~' in linux
        if not path.endswith(os.sep):
            path += os.sep # ensure '/' is present on the end

        class MaxLinesReached(Exception): pass
        class TerminateSearch(Exception): pass
        
        try:
            self.terminate_search = False
            for f in self.enumerate_files_in_dir(path):
                if self.terminate_search: raise TerminateSearch
                file_path_inserted = False
                f_relative = trim_start(f, path)
                self.status("SEARCHING.. {}".format(f_relative))
                for line,s in self.search_file_for_string(f, string):
                    if self.terminate_search: raise TerminateSearch
                    
                    line_count = self.memo.get_line_count()
                    if line_count >= MAX_RESULTS_LINES:
                        raise MaxLinesReached
    
                    # insert file path line
                    if not file_path_inserted:
                        self.memo.set_text_line(-1, '<{}>:'.format(f_relative))
                        self.search_results[line_count-1] = (f, 0)
                        line_count += 1
                        file_path_inserted = True
                    
                    # insert search result line
                    s = ' <{}>: {}'.format(line+1, s.rstrip())
                    self.memo.set_text_line(-1, s)
                    self.search_results[line_count-1] = (f, line)
                    
                    # set caret
                    if line_count == 2:
                        self.memo.set_caret(s.index(':')+2, 1)
                    
            self.status('FINISHED')
        except TerminateSearch:
            self.search_results.clear()
            self.memo.set_text_all('')
        except MaxLinesReached:
            self.status(f'FINISHED, showing only {MAX_RESULTS_LINES} lines')
        finally:
            self.memo.set_prop(PROP_RO, True)
            self.in_process = False

    def run(self):
        h = dlg_proc(0, DLG_CREATE)
        self.h_dlg = h
        
        width  = 640
        height = 400
        r = app_proc(PROC_COORD_MONITOR, 0)
        x = (r[2]-r[0]) - width
        y = (r[3]-r[1]) - height
        
        dlg_proc(h, DLG_PROP_SET, prop={
            'cap': 'Search Lite',
            'x': x,
            'y': y-320, # subtract taskbar height
            'w': width,
            'h': height,
            'border': DBORDER_TOOL,
            'keypreview': True,
            'on_key_down': self.on_dlg_key_down,
            'on_close': self.on_dlg_close,
        })
        
        n = dlg_proc(h, DLG_CTL_ADD, prop='label')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'status',
            'align': ALIGN_TOP,
            'sp_a': 5,
            'cap': 'READY',
        })
        
        n = dlg_proc(h, DLG_CTL_ADD, prop='panel')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'panel',
            'h': 25,
            'align': ALIGN_TOP,
            'sp_a': 5,
        })
        
        n = dlg_proc(h, DLG_CTL_ADD, prop='editor_combo')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'input',
            'p': 'panel',
            'align': ALIGN_CLIENT,
            'texthint': 'Search...',
        })
        val = ed.get_text_sel()
        self.input = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=n))
        self.input.set_text_all(val)
        self.input.set_prop(PROP_FONT, 'default')
        #self.input.set_prop(PROP_COMBO_ITEMS, '1\n2\n3')

        n = dlg_proc(h, DLG_CTL_ADD, prop='editor_combo')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'path',
            'p': 'panel',
            'sp_l': 5,
            'w': 300,
            'align': ALIGN_RIGHT,
            'texthint': 'Path...',
            'val': val,
        })
        val = os.path.dirname(ed.get_filename())
        self.path = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=n))
        self.path.set_text_all(val)
        self.path.set_prop(PROP_FONT, 'default')
        
        n = dlg_proc(h, DLG_CTL_ADD, prop='editor')
        dlg_proc(h, DLG_CTL_PROP_SET, index=n, prop={
            'name': 'memo',
            'align': ALIGN_CLIENT,
            'sp_a': 5,
            'on_click_dbl': self.on_click_dbl,
        })
        self.memo = Editor(dlg_proc(h, DLG_CTL_HANDLE, index=n))
        self.memo.set_prop(PROP_GUTTER_FOLD, True)
        self.memo.set_prop(PROP_WRAP, False)
        self.memo.set_prop(PROP_UNDO_LIMIT, 0)
        self.memo.set_prop(PROP_GUTTER_NUM, False)
        self.memo.set_prop(PROP_HILITE_CUR_LINE, True)
        self.memo.set_prop(PROP_HILITE_CUR_LINE_IF_FOCUS, True)
        
        dlg_proc(h, DLG_SCALE)
        dlg_proc(h, DLG_SHOW_NONMODAL)

    def search_file_for_string(self, file_path, search_string):
        app_idle()
        
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb < MAX_FILE_SIZE_MB and not is_hidden(file_path):        
            try:
                encoding='utf-8'
                if open(file_path, mode='rb').read(3).startswith(BOM):
                    encoding='utf-8-sig'
                with open(file_path, 'r',encoding=encoding) as file:
                    for line,s in enumerate(file):
                        if search_string.lower() in s.lower():
                            yield (line, s)
            except (PermissionError, UnicodeDecodeError, OSError):
                pass
    
    def enumerate_files_in_dir(self, directory):
        app_idle()
        for d in DO_NOT_SEARCH:
            if d in directory.split(os.sep):
                return []
        
        try:
            for file in os.listdir(directory):
                path = os.path.join(directory, file)
                if os.path.isfile(path):
                    yield path
                else:
                    if not is_hidden(path):
                        # TODO: test with symlinks (recursion)
                        yield from self.enumerate_files_in_dir(path)
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            pass

    def on_exit(self, ed_self):
        self.terminate_search = True

