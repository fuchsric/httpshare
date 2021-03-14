#!/usr/bin/env python3
import os, glob, fnmatch, shlex, secrets, threading, re, urllib.parse, html, stun, shutil, traceback, argparse
from socketserver import ThreadingMixIn
from http.server import BaseHTTPRequestHandler, HTTPServer
from http import HTTPStatus
from inspect import signature
from email.utils import parsedate_to_datetime, formatdate


##########################################################################
#                                                                        #
#                               globals                                  #
#                                                                        #
##########################################################################

secret = secrets.token_urlsafe(nbytes=6)

shares = {}
logs = []
lock = threading.Lock()
port = 8000
address = "http://localhost"


##########################################################################
#                                                                        #
#                               utilitys                                 #
#                                                                        #
##########################################################################

def update_address():
    global address
    nat_type, external_ip, external_port = stun.get_ip_info()
    if not external_ip:
        address = "http://localhost"
        return
    if ":" in external_ip:
        external_ip = f"[{external_ip}]"
    address = f"http://{external_ip}"


def format_address():
    if address.endswith("/"):
        return f"{address}{secret}/"
    else:
        return f"{address}:{port}/{secret}/"


# natural_sort() code from https://stackoverflow.com/a/4836734
# originally from https://blog.codinghorror.com/sorting-for-humans-natural-sort-order/
def natural_sort(l):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ]
    return sorted(l, key = alphanum_key)

index_template = """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<title>Directory listing for {}</title>
</head>
<body>
<h1>Directory listing for {}</h1>
<hr>
<ul>
{}
</ul>
<hr>
</body>
</html>
"""

def make_index(names):
    directory = f"/{secret}/"
    lst = []
    for i in natural_sort(names):
        lst.append(f"<li><a href=\"{urllib.parse.quote(i)}\">{html.escape(i)}</a></li>")
    return index_template.format(directory, directory, "\n".join(lst))

def parse_range(r):
    m = re.match(r'bytes=(\d+)-(\d*)$', r.strip().lower())
    if not m:
        return None, None
    if m[2] == "":
        try:
            L = int(m[1])
        except ValueError:
            return None, None
        return L, None
    try:
        L, R = int(m[1]), int(m[2])
    except ValueError:
        return None, None
    return L, R


##########################################################################
#                                                                        #
#                                server                                  #
#                                                                        #
##########################################################################

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        msg = f"{self.address_string()} - - [{self.log_date_time_string()}] {fmt%args}"
        with lock:
            logs.append(msg)
            while len(logs) > 100:
                logs.pop(0)

    def do_HEAD(self):
        try:
            self.process(send_body=False)
        except Exception as e:
            self.log_exception(e)

    def do_GET(self):
        try:
            self.process(send_body=True)
        except Exception as e:
            self.log_exception(e)

    def log_exception(self, e):
        msg = "".join(traceback.format_exception(type(e), e, None)).strip()
        self.log_message("%s", msg)

    def process(self, send_body):
        if self.path == "/robots.txt":
            robots = b"User-agent: *\r\nDisallow: /\r\n"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(robots)))
            self.end_headers()
            if send_body:
                self.wfile.write(robots)
            return
        if not self.path.startswith(f"/{secret}/"):
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if self.path == f"/{secret}/":
            with lock:
                names = list(shares.keys())
            index = make_index(names).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(index)))
            self.end_headers()
            if send_body:
                self.wfile.write(index)
            return

        name = urllib.parse.unquote(self.path.split("/")[-1])
        with lock:
            filepath = shares.get(name, None)
        if not filepath or not os.path.isfile(filepath):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        file_mtime = os.path.getmtime(filepath)
        file_size = os.path.getsize(filepath)
        if file_size == 0:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if "If-Modified-Since" in self.headers:
            try:
                ims_str = self.headers["If-Modified-Since"]
                ims = email.utils.parsedate_to_datetime(ims_str).timestamp()
                if ims >= file_mtime or ims_str == formatdate(file_mtime, usegmt=True):
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.end_headers()
                    return
            except:
                pass
        if "Range" in self.headers:
            L, R = parse_range(self.headers["Range"])
            if R is None:
                R = file_size - 1
            if L is None or L >= file_size or R >= file_size or L > R:
                self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                return
            range_len = R - L + 1
            self.send_response(HTTPStatus.PARTIAL_CONTENT)
            self.send_header('Content-Range', f"bytes {L}-{R}/{file_size}")
            self.send_header('Content-Length', str(range_len))
            self.send_header('Last-Modified', formatdate(file_mtime, usegmt=True))
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            if send_body:
                with open(filepath, "rb") as f:
                    f.seek(L)
                    while range_len > 0:
                        buf = f.read(min(16*1024, range_len))
                        if not buf:
                            break
                        range_len -= len(buf)
                        self.wfile.write(buf)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Last-Modified", formatdate(file_mtime, usegmt=True))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        if send_body:
            with open(filepath, "rb") as f:
                shutil.copyfileobj(f, self.wfile)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

def serv():
    server = ThreadedHTTPServer(('', port), Handler)
    server.serve_forever()


##########################################################################
#                                                                        #
#                               commands                                 #
#                                                                        #
##########################################################################

def command_pwd():
    """print the current working directory"""
    print(os.getcwd())

def command_tail():
    """print log of recent requests"""
    with lock:
        for msg in logs:
            print(msg)

def command_cd(arg):
    """change directory"""
    try:
        i = glob.iglob(arg)
        d = next(i, None)
        d2 = next(i, None)
        if d is None:
            print("no directory matched")
        elif d2 is not None:
            print("more than one directory matched")
        else:
            os.chdir(d)
    except OSError as e:
        print(e)
    print(os.getcwd())

def command_dir():
    """list directory contents"""
    dirs = []
    files = []
    for i in os.scandir():
        if i.is_dir():
            dirs.append(i.name + os.path.sep)
        elif i.is_file():
            files.append(i.name)
    for i in natural_sort(dirs):
        print(i)
    for i in natural_sort(files):
        print(i)

def command_add(arg):
    """add files matching pattern to share"""
    added = []
    with lock:
        for i in glob.iglob(arg):
            if os.path.isfile(i) and os.path.getsize(i) > 0:
                filename = os.path.basename(i)
                filepath = os.path.abspath(i)
                shares[filename] = filepath
                added.append(i)
    print(f"added {len(added)} files:")
    for i in natural_sort(added):
        print(i)

def command_del(arg):
    """remove files matching pattern from share"""
    removed = []
    with lock:
        for i in [j for j in shares if fnmatch.fnmatch(j, arg)]:
            shares.pop(i)
            removed.append(i)
    print(f"removed {len(removed)} files:")
    for i in natural_sort(removed):
        print(i)

def command_list():
    """display direct links to shared files"""
    with lock:
        names = list(shares.keys())
    print(f"{len(names)} files are being shared")
    for i in natural_sort(names):
        print(f"{format_address()}{urllib.parse.quote(i)}")

def command_stun():
    """identify servers external ip address"""
    update_address()
    print(f"server availible here: {address}:{port}/{secret}/")


def command_setaddress(arg):
    """manually set servers address; a trailing '/' deactivates addition of port number"""
    global address
    address = arg


def command_help():
    """display list of commands"""
    print("available commands are:")
    print()
    prefix = "command_"
    for name, obj in globals().items():
        if not name.startswith(prefix):
            continue
        names = [name[len(prefix):]]
        for k, v in sorted(aliases.items()):
            if v == names[0]:
                names.append(k)
        print(f"{', '.join(names)}:")
        argc = len(signature(obj).parameters)
        if argc > 0:
            print(f"\targuments: {argc}")
        print(f"\t{obj.__doc__}")
        print()

aliases = {
    "+": "add",
    "-": "del",
    "d": "del",
    "lst": "list",
    "ls": "dir",
    "l": "list",
    "log": "tail",
    "set": "setaddress",
    "q": "exit"
}

def execute(cmd):
    if len(cmd) == 0:
        return True
    cmd, args = cmd[0], cmd[1:]
    if cmd in aliases:
        cmd = aliases[cmd]
    if cmd == 'exit':
        return False
    f = globals().get("command_" + cmd, None)
    if f is None:
        print(f"invalid command \"{cmd}\"")
        return False
    argc = len(signature(f).parameters)
    if len(args) != argc:
        print(f"{cmd} needs {argc} arguments ({len(args)} given)")
    try:
        f(*args)
    except Exception as e:
        print(e)
    return True


##########################################################################
#                                                                        #
#                                 main                                   #
#                                                                        #
##########################################################################

def main():
    global port
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default=port, type=int, help='http port')
    parser.add_argument('-c', nargs='+', default=[], action='append', help='execute command on startup', metavar=("COMMAND", "ARGUMENT"))
    args = parser.parse_args()
    port = args.port
    for cmd in args.c:
        execute(cmd)
    try:
        thread = threading.Thread(target=serv, daemon=True)
        thread.start()
        print(f"server availible here: {format_address()}")
        while True:
            cmd = shlex.split(input(">"))
            if not execute(cmd):
                break
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
