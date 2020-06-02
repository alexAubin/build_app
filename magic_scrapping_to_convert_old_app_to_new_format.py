import shlex
import sys
import os
import re

class Script():

    def __init__(self, app_path, name):
        self.name = name
        self.app_path = app_path
        self.path = app_path + "/scripts/" + name
        self.lines = list(self.read_file())

    def read_file(self):
        with open(self.path) as f:
            lines = f.readlines()

        # Remove trailing spaces, empty lines and comment lines
        lines = [line.strip() for line in lines]
        lines = [line for line in lines if line and not line.startswith('#')]

        # Merge lines when ending with \
        lines = '\n'.join(lines).replace("\\\n", "").split("\n")

        for line in lines:
            try:
                yield shlex.split(line, True)
            except Exception as e:
                pass


    def contains(self, command):
        return any(command in line
                   for line in [' '.join(line) for line in self.lines])

    def containsregex(self, regex):
        return any(re.search(regex, line)
                   for line in [' '.join(line) for line in self.lines])

    def findall(self, regex):
        res = [re.search(regex, line)
               for line in [' '.join(line) for line in self.lines]]
        return [r.groups() for r in res if r]

    def first(self, regex):
        for stuff in (re.search(regex, line)
                for line in [' '.join(line) for line in self.lines]):
            if stuff:
                return stuff



install = Script(sys.argv[1], "install")
resources = []

for match in install.findall(r"(\w+)=.*ynh_find_port.*?[^0-9]([0-9]{3,})"):

    r = {
        "type": "port",
        "name": match[0],
        "default": match[1] or 1234,
        "exposure": "internal"
    }

    if install.contains(r"firewall allow.*\$%s" % r["name"]):
        r["exposure"] = "external"

    resources.append(r)

if install.contains("final_path="):
    match = install.first(r"final_path=['\"]?(.*)[^'\"]?$").groups()

    # TODO: leacy alias
    r = {
        "type": "directory",
        "name": "install_dir",
        "directory": match[0]
    }

    resources.append(r)

if install.contains("ynh_webpath_register"):

    r = {
        "type": "url",
        "name": "url",
        "settings": ["domain", "path"],
        "from_manifest": True
    }

    resources.append(r)

if install.contains("ynh_system_user_create"):
    #for example: ynh_system_user_create --username=$synapse_user --home_dir=/var/lib/matrix-$app
    match = install.first("ynh_system_user_create.*").group().split()
    if len(match) >= 2:
        match[1] = match[1].split("=")[-1].strip("\"'")
    if len(match) >= 3:
        match[2] = match[2].split("=")[-1].strip("\"'")

    r = {
        "name": "user",
        "type": "system_user",
        "user": match[1] if len(match) >= 2 else "$app",
        "home": match[2] if len(match) >= 3 else None
    }

    resources.append(r)

for r in resources:
    print(r)


## This will provision a mysql DB and create settings "db_name", "db_user", "db_pwd"
##[[resource]]
##name = "db"
##type = "db_mysql"
##settings = ["db_name", "db_user", "db_pwd"]
#
