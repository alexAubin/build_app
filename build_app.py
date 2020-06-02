#!/usr/bin/env python3
import sys
import toml
import json
import jinja2
import os
import glob

scripts = ["install", "remove", "backup", "restore", "upgrade"]


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
        self.code = {s: "" for s in scripts}
        overrides = {s: {} for s in scripts}

        for override in kwargs.pop("override", []):
            override_script_list = override.pop("scripts", [])
            before = override.pop("before", None)
            code = override.pop("code", None)
            after = override.pop("after", None)
            for script in override_script_list:
                overrides[script].update(override)
                if after:
                    after = "\n".join([line.strip() for line in after.split("\n")])
                    self.after[script] = after  # To be discussed: could be += here
                if before:
                    before = "\n".join([line.strip() for line in before.split("\n")])
                    self.before[script] = before  # To be discussed: could be += here
                if code:
                    code = "\n".join([line.strip() for line in code.split("\n")])
                    self.code[script] = code  # To be discussed: could be += here

        for script in scripts:

            if self.code[script]:
                continue

            template_for_this_script = "steps/%s/%s.j2" % (self.type, script)
            if os.path.exists(template_for_this_script):
                self.code[script] = open(template_for_this_script).read()

        for script in scripts:

            args_for_this_script = args.copy()
            args_for_this_script.update(overrides[script])

            code_template = self.before[script] + "\n" + self.code[script] + "\n" + self.after[script]
            self.code[script] = render_template_string(code_template.strip(), **args_for_this_script)


def main():
    target = sys.argv[1]
    assert target

    manifest = json.load(open(target + "/manifest.json"))
    resources = toml.load(target + "/resources.toml")["resource"]
    steps = toml.load(target + "/steps.toml")["step"]

    # Extra special "globals" step
    globals_ = [s for s in steps if s.get("type") == "globals"]
    globals_ = globals_[0] if globals_ else None
    steps = [s for s in steps if s.get("type") != "globals"]

    resources = [Resource(**r) for r in resources]
    steps = [Step(**s) for s in steps]

    files_to_source = []
    if os.path.exists(target + "/scripts/_common.sh"):
        files_to_source += ["_common.sh"]
    files_to_source = [os.path.basename(f) for f in glob.glob(target + "/scripts/ynh_*")]

    for script in scripts:

        # Upgrade require more thoughts, skipping for now
        if script == "upgrade":
            continue

        open(target + "/scripts/" + script, "w").write(render_template_file(
            "scripts/%s.j2" % script,
            globals_=globals_,
            files_to_source=files_to_source,
            manifest=manifest,
            resources=resources,
            steps=steps
        ))


main()
