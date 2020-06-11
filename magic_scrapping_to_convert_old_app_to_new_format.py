#!/usr/bin/python3

import shlex
import sys
import os
import re
import toml

helpers_replace = {
    "yunohost service add": "ynh_service_add",
    "ynh_exec_fully_quiet": "",
    "ynh_exec_warn_less": "",
    "ynh_clean_setup": "",
    "yunohost firewall allow": "ynh_firewall_allow",
    "--no-upnp": "",
    "ynh_clean_check_starting": "",
    "ynh_abort_if_errors": "",
}

helpers_pos = {
    'ynh_install_app_dependencies': ["dep+"],
    'ynh_local_curl': ["page_uri", "args+"],
    'ynh_mysql_connect_as': ["stdin"],
    'ynh_secure_remove': ["file"],
    'ynh_service_add': ["name"],
    'ynh_add_nginx_config': ["extra_vars+"],
    "ynh_firewall_allow": ["protocol", "port"],
    "ynh_replace_string": ["match_string", "replace_string", "target_file"],
    "ynh_add_systemd_config": ["service", "template"],
    "ynh_print_info": ["message"],
    "ynh_webpath_register": ["app", "domain", "path_url"],
    "ynh_webpath_available": ["domain", "path_url"],
    "ynh_app_setting_set": ["app", "key", "value"],
    "ynh_app_setting_delete": ["app", "key"],
    "ynh_psql_setup_db": ["db_name", "db_user", "db_pwd"],
    "ynh_setup_source": ["dest_dir", "source_id"],
    "ynh_system_user_create": ["username", "home_dir"],
    "ynh_store_file_checksum": ["_"],
    "ynh_install_nodejs": ["nodejs_version"],
}

helpers_shortargs = {
    'ynh_systemd_action': { "-n": "--service_name=", "-a": "--action=", "-l": "--line_match=", "-p": "--log_path=" }
}

class Script():

    def __init__(self, app_path, name):
        self.name = name
        self.app_path = app_path
        self.path = app_path + "/scripts/" + name
        self.lines = list(self.read_file())

    def dump(self):
        for line in self.lines:
            if isinstance(line, dict):
                if line["helper"] in ["ynh_print_info", "ynh_script_progression"] and "message" in line:
                    print("================================")
                    print(line["message"])
                    print("================================")
                else:
                    print(line)
            else:
                print(" ".join(line))

    def read_file(self):
        with open(self.path) as f:
            lines = f.readlines()

        # Remove trailing spaces, empty lines and comment lines
        lines = [line.strip() for line in lines]
        lines = [line for line in lines if line and not line.startswith('#')]

        # Merge lines when ending with \
        lines = '\n'.join(lines).replace("\\\n", "").split("\n")

        for line in lines:

            for pattern, replace in helpers_replace.items():
                line = line.replace(pattern, replace)

            if line.startswith("ynh_"):
                shortargs = helpers_shortargs.get(line.strip().split()[0], {})
                for short, long_ in shortargs.items():
                    line = line.replace(" %s " % short, (" %s" % long_) if long_.endswith("=") else (" %s " % long_))

            try:
                parsed_line = shlex.split(line, True)
            except Exception as e:
                pass

            def parse_positionals(cmd):

                if cmd["positionals"]:
                    if cmd["helper"] not in helpers_pos:
                        print("Not sure what to do with %s" % cmd)
                        return

                    helper_pos = helpers_pos[cmd["helper"]]
                    helper_pos_i = 0
                    for name in cmd:
                        if name in helper_pos:
                            del helper_pos[name]
                    for pos in cmd["positionals"]:
                        if pos in ["<", "<<<", "2>&1"]:
                            continue

                        name = helper_pos[helper_pos_i]
                        if name.endswith("+"):
                            name = name.strip("+")
                            if not name in cmd:
                                cmd[name] = []
                            cmd[name].append(pos)
                        else:
                            cmd[name] = pos
                            helper_pos_i += 1

                del cmd["positionals"]

            if not " ".join(parsed_line).strip(" (){}"):
                continue

            if parsed_line[0].startswith("ynh"):

                command = {"helper": parsed_line[0], "positionals": []}

                args_for = "positionals"
                for element in parsed_line[1:]:
                    if element.startswith("--"):
                        if "=" in element:
                            name, value = element.split("=",1)
                            command[name.strip("--")] = value
                        else:
                            args_for = element.strip("--")
                            command[args_for] = []
                    else:
                        command[args_for].append(element)
                try:
                    parse_positionals(command)
                except Exception as e:
                    print(command)
                    raise
                yield command
            else:
                yield parsed_line

    def contains(self, command):
        return any(command in line
                   for line in [' '.join(line) for line in self.lines])

    def containsregex(self, regex):
        return any(re.search(regex, line)
                   for line in [' '.join(line) for line in self.lines])

    def findall(self, regex):
        res = [re.search(regex, line)
               for line in [' '.join(line) for line in self.lines]]
        return [r for r in res if r]

    def first(self, regex):
        for stuff in (re.search(regex, line)
                for line in [' '.join(line) for line in self.lines]):
            if stuff:
                return stuff

    def pop_raw_lines(self, match):

        for line in self.lines.copy():
            r = re.search(match, " ".join(line)) if isinstance(line, list) else None
            if r:
                self.lines.remove(line)
                yield (line, r)

    def pop_helper_lines(self, helper, **kwargs):

        for line in self.lines.copy():
            r = (line["helper"] == helper and all(line[k] == v for k, v in kwargs.items())) if isinstance(line, dict) else None
            if r:
                self.lines.remove(line)
                yield line


install = Script(sys.argv[1], "install")

resources_hooks = []
def resource(from_raw=None, from_helper=None, **kwargs):
    def decorator(function):
        def wrapper(*args, **kwargs):
            if from_raw:
                raw_lines = list(install.pop_raw_lines(from_raw))
                for line, match in raw_lines:
                    yield function(line, match)
            elif from_helper:
                raw_lines = list(install.pop_helper_lines(from_helper, **kwargs))
                for match in raw_lines:
                    yield function(match)
            else:
                raise Exception("Uh wut?")
        resources_hooks.append(wrapper)
        return wrapper
    return decorator

steps_hooks = []
def step(from_raw=None, from_helper=None, **kwargs):
    def decorator(function):
        def wrapper(*args, **kwargs):
            if from_raw:
                raw_lines = list(install.pop_raw_lines(from_raw))
                for line, match in raw_lines:
                    yield function(line, match)
            elif from_helper:
                raw_lines = list(install.pop_helper_lines(from_helper, **kwargs))
                for match in raw_lines:
                    yield function(match)
            else:
                raise Exception("Uh wut?")
        steps_hooks.append(wrapper)
        return wrapper
    return decorator

@resource(from_raw=r"(?P<name>\w+)=.*ynh_find_port.*?[^0-9](?P<port>[0-9]{3,})")
def port(line, match):

    return {
        "type": "port",
        "name": match.group("name"),
        "default": match.group("port") or 1234,
        "exposure": "external" if any(install.pop_helper_lines("ynh_firewall_allow")) else "internal"
    }


@resource(from_raw=r"final_path=(?P<dir>.*)$")
def install_dir(line, match):

    all(install.pop_raw_lines(r"^test .*final_path.*$"))

    return {
        "type": "directory",
        "name": "install_dir",
        "directory": match.group("dir")
    }

    # TODO: legacy alias


@resource(from_helper="ynh_webpath_register")
def url(match):

    all(install.pop_helper_lines(r"ynh_webpath_available"))

    return {
        "type": "url",
        "name": "url",
        "settings": ["domain", "path"],
        "from_manifest": True
    }


@resource(from_helper="ynh_system_user_create")
def url(match):

    return {
        "name": "user",
        "type": "system_user",
        "user": match.get("username", "$app"),
        "home": match.get("home_dir")
    }


@resource(from_helper="ynh_mysql_setup_db")
def db_mysql(match):

    return {
        "name": "db",
        "type": "db_mysql",
        "settings": ["db_name", "db_user", "db_pwd"]
    }


@resource(from_helper="ynh_psql_setup_db")
def db_psql(match):

    all(install.pop_helper_lines("ynh_psql_test_if_first_run"))

    return {
        "name": "db",
        "type": "db_psql",
        "settings": ["db_name", "db_user", "db_pwd"]
    }

resources = []
for hook in resources_hooks:
    resources += list(hook())

#
# Global vars
#

global_vars = {}
for line, _ in install.pop_raw_lines(r"^(export )?\w+=.*$"):

    name, value = " ".join(line).split("=", 1)
    if name in global_vars:
        print("Multiple definitions for var %s" % name)
    else:
        global_vars[name] = value

#
# Confs
#

confs = {}

for match in install.pop_helper_lines("ynh_replace_string"):

    if not match:
        continue

    f = match["target_file"]

    # If f is something like "$foo", try to identify what's the value behind it... (foo=bar)
    orig_f = f
    if f.startswith("$") and f[1:] in global_vars:
        f = global_vars[f[1:]]

    if not f in confs:
        confs[f] = {"replaces": []}
    keyword = match["match_string"].strip("_").lower()
    confs[f]["replaces"].append(keyword)
    confs[f]["alias"] = orig_f

for f, conf in confs.copy().items():
    cp_line = next(install.pop_raw_lines(r"^cp.*%s.*$" % re.escape(f)), None) or next(install.pop_raw_lines(r"^cp.*%s.*$" % re.escape(conf["alias"])), None)
    if cp_line:
        line = [l for l in cp_line[0] if not l.startswith("-")]
        src = line[1]
        dest = line[2]

        # If dest is something like "$foo", try to identify what's the value behind it (foo=bar)
        if dest.startswith("$") and dest[1:] in global_vars:
            dest = global_vars[dest[1:]]

        if f == src:
            conf = confs[src]
        else:
            conf = confs[src] = confs[dest]
            del confs[dest]

        conf["dest"] = dest

#
# Steps
#

@step(from_helper="ynh_install_app_dependencies")
def deps_apt(match):

    deps = match.get("dep")

    if len(deps) == 1 and deps[0].startswith("$"):
        deps = deps[0]

    return {
        "type": "dependencies_apt",
        "deps": deps
    }

@step(from_helper="ynh_install_nodejs")
def dep_nodejs(match):

    all(install.pop_helper_lines("ynh_use_nodejs"))

    return {
        "type": "dependencies_nodejs",
        "version": match.get("nodejs_version")
    }

@step(from_helper="ynh_setup_source")
def sources(match):

    return {
        "type": "sources",
        "install_dir": match.get("dest_dir", "$install_dir").replace("final_path", "install_dir"),
        "source_id": match.get("source_id")
    }

@step(from_helper="ynh_add_fpm_config")
def conf_phpfpm(match):

    return {
        "type": "conf_phpfpm",
        "usage": match.get("usage"),
        "footprint": match.get("footprint")
    }

@step(from_helper="ynh_add_systemd_config")
def conf_service(match):

    s = {
        "type": "conf_service",
        "service": match.get("service", "$app"),
        "template": match.get("template")
    }

    for service_add_match in install.pop_helper_lines("ynh_service_add", name=s["service"]):
        s["integrate_in_yunohost"] = True
        s["logs"] = service_add_match.get("log", [])

    if "../conf/systemd.service" in confs:
        s["basic_pre_replace"] = confs.pop("../conf/systemd.service").get("replaces")

    return s

@step(from_helper="ynh_systemd_action", action="start")
def start_service(match):

    return {
        "type": "start_service",
        "service": match.get("service_name", "$app"),
        "wait_until": match.get("line_match")
    }

@step(from_helper="ynh_use_logrotate")
def conf_logrotate(match):

    return {
        "type": "conf_logrotate",
        "log": match.get("logfile")
    }

@step(from_helper="ynh_add_fail2ban_config")
def conf_fail2ban(match):

    return {
        "type": "conf_fail2ban",
        "log": match.get("logpath"),
        "failregex": match.get("failregex"),
        "max_retry": match.get("max_retry")
    }

@step(from_helper="ynh_add_nginx_config")
def conf_nginx(match):

    s = {
        "type": "conf_nginx"
    }

    if "../conf/nginx.conf" in confs:
        s["basic_pre_replace"] = confs.pop("../conf/nginx.conf").get("replaces")

    elif "/etc/nginx/conf.d/$domain.d/$app.conf" in confs:
        s["basic_pre_replace"] = confs.pop("/etc/nginx/conf.d/$domain.d/$app.conf").get("replaces")

    all(install.pop_helper_lines("ynh_systemd_action", service_name="nginx", action="reload"))
    all(install.pop_raw_lines(r"systemctl reload nginx"))

    return s


@step(from_raw=r"if.*\$is_public")
def conf_ssowat(line, match):

    # TODO : extra perms

    s = {
        "type": "conf_ssowat"
    }

    all(install.pop_helper_lines("ynh_permission_update", permission=["main"]))
    all(install.pop_helper_lines("ynh_app_setting_delete", key="unprotected_uris"))
    all(install.pop_raw_lines(r"yunohost app ssowatconf"))

    return s

steps = []
for hook in steps_hooks:
    steps += list(hook())

for name, conf in confs.items():

    if not "dest" in conf:
        print("Not sure what to do with conf %s ? (%s)" % (name, conf))
        continue

    s = {
        "type": "conf",
        "template": name,
        "destination": conf["dest"],
        "basic_pre_replace": conf["replaces"]
    }

    def where_to_insert():
        for i, step in enumerate(steps):
            if step["type"] == "sources":
                return i+1
            elif step["type"] == "conf_service":
                return i
        print("Not sure where to add step for custom conf... adding at the beginning")
        return 0

    steps.insert(where_to_insert(), s)

all(install.pop_raw_lines(r"^source .*$"))
all(install.pop_raw_lines(r"^(export )?\w+=\$YNH_APP_[_A-Z0-9]+$"))
all(install.pop_helper_lines("ynh_store_file_checksum"))
all(install.pop_helper_lines("ynh_app_setting_set"))

print(toml.dumps({"resource": resources}))
print(toml.dumps({"step": steps}))
install.dump()


