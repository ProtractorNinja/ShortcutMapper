import os
import json
import copy
import collections
import glob
import codecs

import keynames
from constants import *
from logger import getlog
log = getlog()


class Shortcut(object):
    def __init__(self, name, key, mods=[], anymod=False):
        self.name = name
        self.key = key
        self.mods = mods
        self.anymod = anymod

    def serialize(self):
        mods = list(set(self.mods))
        mods.sort()
        mods_str = json.dumps(mods)

        return '{"name":"%s", "mods":%s}' % (self.name, mods_str)

    def __str__(self):
        return self.serialize()


class ShortcutContext(object):
    def __init__(self, name):
        self.name = name
        self.shortcuts = []
        self.added_shortcuts_lookup = []
        self.added_keycombos_lookup = []
        self.added_keycombo_to_shortcuts_lookup = {}

    def add_shortcut(self, s, check_for_duplicates=True):
        log.debug("adding shortcut %s", self._get_shortcut_str(s))

        # Validate modifier names
        # Modifier keys cannot be ambiguous (ctrl -> left_ctrl, right_ctrl), but can be added later if needed
        valid_mod_names = []
        for mod in s.mods:
            valid_mod_keys = keynames.get_valid_keynames(mod)
            if len(valid_mod_keys) == 0:
                log.warn('...skipping add shortcut because it has an invalid modifier key name (%s)', mod)
                return
            assert len(valid_mod_keys) == 1, "Ambiguous modifier keys not supported yet"
            valid_mod_names.append(valid_mod_keys[0])
        s.mods = valid_mod_names

        # Split up ambiguous keys into multiple shortcuts
        #  a simple example is +, which can be PLUS or NUMPAD_PLUS
        expanded_shortcuts = []
        keys = keynames.get_valid_keynames(s.key)
        if len(keys) == 0:
            log.warn('...skipping add shortcut because it has an invalid key name (%s)', s.key)
            return

        for key in keys:
            # if anymod can be used, split it up into individual shortcuts
            if s.anymod:
                for mod in s.mods:
                    s_expanded = Shortcut(s.name, key, [mod])
                    expanded_shortcuts.append(s_expanded)
            else:
                s_expanded = copy.deepcopy(s)
                s_expanded.key = key
                expanded_shortcuts.append(s_expanded)

        # Add all expanded shortcuts
        for shortcut in expanded_shortcuts:
            shortcut_str = self._get_shortcut_str(shortcut)
            keycombo_str = self._get_keycombo_str(shortcut)

            if not check_for_duplicates:
                self.shortcuts.append(shortcut)
                self.added_shortcuts_lookup.append(shortcut_str)
                self.added_keycombo_to_shortcuts_lookup[keycombo_str] = shortcut_str
                continue

            # Don't Add Duplicates
            if keycombo_str in self.added_keycombo_to_shortcuts_lookup.keys():
                existing_shortcut = self.added_keycombo_to_shortcuts_lookup[keycombo_str]
                log.warn('Warning: shortcut with keycombo %s already exists in context\n' +
                    '   ...existing shortcut is: %s\n   ...skipping add shorcut: "%s"',
                    keycombo_str, existing_shortcut, shortcut.name)
                continue

            if len(expanded_shortcuts) > 1:
                log.debug('   ...expanding into %s', shortcut_str)
            self.shortcuts.append(shortcut)
            self.added_shortcuts_lookup.append(shortcut_str)
            self.added_keycombo_to_shortcuts_lookup[keycombo_str] = shortcut_str

    def _get_shortcut_str(self, shortcut):
        keys = list(shortcut.mods)
        keys.sort()
        keys.append(shortcut.key)

        anymod = ''
        if shortcut.anymod:
            anymod = ' (Any Mod)'

        return ('"' + shortcut.name + '"').ljust(45) + '+'.join(keys) + anymod

    def _get_keycombo_str(self, shortcut):
        keys = list(shortcut.mods)
        keys.sort()
        keys.append(shortcut.key)
        return '+'.join(keys)


    def serialize(self):
        # todo: check for duplicates somewhere else!
        lookup_table = {}
        for shortcut in self.shortcuts:
            if shortcut.key not in lookup_table.keys():
                lookup_table[shortcut.key] = []
            lookup_table[shortcut.key].append(shortcut)

        output_str = '"%s" : {\n' % (self.name)

        sorted_shortcuts = collections.OrderedDict(sorted(lookup_table.items()))
        for key, shortcuts in sorted_shortcuts.items():
            output_str += '    "%s" : [\n' % (key)

            # Important to sort shortcuts alphabetically, this improves the quality of repo diffs
            serialized_shortcuts = [s.serialize() for s in shortcuts]
            serialized_shortcuts.sort()
            for shortcut_str in serialized_shortcuts:
                output_str += '        %s,\n' % (shortcut_str)

            output_str = output_str.rstrip(',\n')
            output_str += '\n    ],\n'
        output_str = output_str.rstrip(',\n')

        output_str += '\n}'

        return output_str





class ApplicationConfig(object):
    def __init__(self, app_name, app_version, app_os):
        super(ApplicationConfig, self).__init__()
        self.name = app_name
        self.version = app_version
        self.os = app_os
        self.contexts = {}

    def get_or_create_new_context(self, name):
        """Gets an existing context by name, or adds a new one to the application"""

        if name in self.contexts.keys():
            return self.contexts[name]

        context = ShortcutContext(name)
        self.contexts[context.name] = context
        return context

    def get_mods_used(self):
        mods_used = []
        for context in self.contexts.values():
            for shortcut in context.shortcuts:
                for mod in shortcut.mods:
                    if mod not in mods_used:
                        mods_used.append(mod)
        return sorted(mods_used)

    def serialize(self, output_dir):
        assert os.path.isdir(output_dir), "The output dir is not a directory"
        assert self.os in VALID_OS_NAMES, "The application Operating system must be one of these: " + str(VALID_OS_NAMES)
        assert self.version is not None and len(self.version) > 0, "The application version must be assigned"

        appname_for_file = self.name.lower().replace(' ', '-')
        output_path = os.path.join(output_dir, "{0}_{1}_{2}.json".format(appname_for_file, self.version, self.os))
        log.info('serializing ApplicationConfig to %s', output_path)

        mods_used = self.get_mods_used()

        output_str = u'{\n'
        output_str += u'    "name" : "%s",\n' % (self.name)
        output_str += u'    "version" : "%s",\n' % (self.version)
        output_str += u'    "os" : "%s",\n' % (self.os)
        output_str += u'    "mods_used" : %s,\n' % (json.dumps(mods_used))
        output_str += u'    "contexts" : {\n'

        contexts_str = u""

        contexts = list(self.contexts.values())
        contexts.sort(key=lambda c: c.name)
        for context in contexts:
            # don't serialize empty contexts
            if len(context.shortcuts) == 0:
                continue

            ctx_str = u'        ' + context.serialize()
            ctx_str = ctx_str.replace(u'\n', u'\n        ')

            contexts_str += ctx_str + u',\n'
        contexts_str = contexts_str.rstrip(u',\n')

        output_str += contexts_str + u'\n'
        output_str += u'    }\n'
        output_str += u'}'

        # Write to file
        file = codecs.open(output_path, encoding='utf-8', mode='w+')
        file.write(output_str)
        file.close()

        # Regenerate apps.js file, this file has a list of all appdata json files
        #  so the web application knows what apps exist
        regenerate_site_apps_js()





def regenerate_site_apps_js():
    log.debug("REGENERATING FILE /gh-pages/javascripts/apps.js")

    class SiteAppDatas:
        def __init__(self):
            self.apps = {}

        def add_app(self, filename, app_name, version, os_name):
            if app_name not in self.apps.keys():
                self.apps[app_name] = {}

            if version not in self.apps[app_name].keys():
                self.apps[app_name][version] = {}

            if os_name not in self.apps[app_name][version].keys():
                self.apps[app_name][version][os_name] = filename

        def to_json(self):
            json_str = '[\n'
            for appname, version_dict in self.apps.items():
                json_str += '    {\n'
                json_str += '        name: "%s",\n' % (appname)
                json_str += '        data: {\n'
                for version, os_dict in version_dict.items():
                    json_str += '            "%s": {\n' % (version)
                    for os_name, filename in os_dict.items():
                        json_str += '                "%s": "%s",\n' % (os_name, filename)
                    json_str += '            },\n'
                json_str += '        }\n'
                json_str += '    },\n'
            json_str += ']'

            return json_str

    apps_js_file = open(PAGES_APPS_JS_FILE, 'w')
    apps_js_file.write("// DO NOT EDIT THIS FILE\n")
    apps_js_file.write("// This file is automatically generated when new ApplicationConfigs are serialized\n")
    apps_js_file.write("// look in /shmaplib/appdata.py at regenerate_site_apps_js()\n\n")

    # Generate JSON for all applications in the specific format we want it
    app_sitedata = SiteAppDatas()
    for path in glob.glob(os.path.join(DIR_PAGES_APPDATA, "*.json")):
        with open(path) as appdata_file:
            appdata = json.load(appdata_file)

            app_name = appdata["name"]
            app_version = appdata["version"]
            app_os = appdata["os"]

            filename = os.path.basename(path)
            app_sitedata.add_app(filename, app_name, app_version, app_os)

    # Write json for all application data
    apps_json = app_sitedata.to_json()
    apps_js_file.write("var sitedata_apps = " + apps_json + ";\n")
    apps_js_file.close()

