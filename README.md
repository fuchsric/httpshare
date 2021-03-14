# httpshare

This project improves on `python -m http.server` to better enable temporary sharing of files over the internet.

These improvements are:
- serving multiple requests in parallel
- support for ranged requests
- protection from crawlers and search-engines
- automatic generation of direct-links
- ability to add/remove files from different directories to/from share during operation


## dependencies

`pip3 install pystun3`
[pystun3](https://pypi.org/project/pystun3/) is used to get the servers external IP, needed for generating direct links


## how-to

After starting, you are prompted with an interactive shell.
You will likely want to
- `cd` into a directory containing files (this supports globbing)
- `add` some or all of them to the share (i.e. `add *.zip`)
- `stun` (this may take a few seconds)
- `list`, to output direct links to all files in the share

The direct links will follow this format: `http://127.0.0.1:8000/B0PmBaT5/Awesome%20Stuff.zip`
where `B0PmBaT5` is a token randomly generated on startup of the script.
Any requests omitting this token will yield a 403 "access denied" response.
The only exception to this is `/robots.txt`, configured to disallow everything.

Please be advised that as httpshare.py uses unencrypted HTTP your ISP, VPN provider, and others (WiFi hotspot owners, employers, parents, etc.) may still record the names and contents of shared files.


### command line parameters

```
usage: httpshare.py [-h] [-p PORT] [-c COMMAND [ARGUMENT ...]]

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  http port
  -c COMMAND [ARGUMENT ...]
                        execute command on startup
```


### available commands

```
pwd:
        print the current working directory

tail, log:
        print log of recent requests

cd:
        arguments: 1
        change directory

dir, ls:
        list directory contents

add, +:
        arguments: 1
        add files matching pattern to share

del, -, d:
        arguments: 1
        remove files matching pattern from share

list, l, lst:
        display direct links to shared files

stun:
        identify servers external ip address

help:
        display list of commands
```
