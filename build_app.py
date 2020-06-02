#!/usr/bin/env python3
import sys
import toml
import json
import jinja2
import os
import glob

scripts = ["install", "remove", "upgrade", "backup", "restore"]


def render_template_file(template_, **kwargs):

    return jinja2.Template(open(template_).read()).render(**kwargs)


def render_template_string(string_, **kwargs):

    return jinja2.Template(string_).render(**kwargs)


class Resource():

    def __init__(self, type, name, settings=None, from_manifest=False, **kwargs):
        self.type = type
        self.name = name
        self.settings = settings if settings is not None else [name]
        self.from_manifest = from_manifest

        meta = toml.load("resources/%s/meta.toml" % self.type)
        args = meta.get("defaults", {})
        args.update(kwargs)

        self.code = {}
        for script in scripts:
            template_for_this_script = "resources/%s/%s.j2" % (self.type, script)
            if not os.path.exists(template_for_this_script):
                continue

            self.code[script] = render_template_file(template_for_this_script, name=name, **args)


class Step():

    def __init__(self, type, **kwargs):

        self.type = type

        meta = toml.load("steps/%s/meta.toml" % self.type)
        args = meta.get("defaults", {})
        args.update(kwargs)

        self.before = {s: "" for s in scripts}
        self.after = {s: "" for s in scripts}
        overrides = {s: {} for s in scripts}

        for override in kwargs.pop("override", []):
            override_script_list = override.pop("scripts", [])
            before = override.pop("before", None)
            after = override.pop("after", None)
            for script in override_script_list:
                overrides[script].update(override)
                if after:
                    self.after[script] = after  # To be discussed: could be += here
                if before:
                    self.before[script] = before  # To be discussed: could be += here

        self.code = {}
        for script in scripts:

            template_for_this_script = "steps/%s/%s.j2" % (self.type, script)
            if not os.path.exists(template_for_this_script):
                continue

            args_for_this_script = args.copy()
            args_for_this_script.update(overrides[script])

            self.before[script] = render_template_string(self.before[script], **args_for_this_script)
            self.code[script] = render_template_file(template_for_this_script, **args_for_this_script)
            self.after[script] = render_template_string(self.after[script], **args_for_this_script)


def main(target):
    target = sys.argv[1]
    manifest = json.load(open(target + "/manifest.json"))
    resources = toml.load(target + "/resources.toml")["resource"]
    steps = toml.load(target + "/steps.toml")
    global_ = steps["global"]

    resources = [Resource(**r) for r in resources]
    steps = [Step(**s) for s in steps["step"]]

    files_to_source = []
    if os.path.exists(target + "/scripts/_common.sh"):
        files_to_source += ["_common.sh"]
    files_to_source = [os.path.basename(f) for f in glob.glob(target + "/scripts/ynh_*")]

    print(render_template_file(
        "scripts/install.j2",
        script="install",
        global_=global_,
        files_to_source=files_to_source,
        manifest=manifest,
        resources=resources,
        steps=steps
    ))


main()
