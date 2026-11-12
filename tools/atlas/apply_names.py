# Apply Caduceus atlas.json + autonames.json names to your own Ghidra import of an OM/Olympus main image.
# Runs under PyGhidra (Ghidra 11.3+/12) or Jython (older Ghidra); same rules as ApplyNames.java.
#
#   script args: <atlas.json|-> [autonames.json|-] [-create] [-comments] [-force] [-min-conf low|medium|high]
#   (no args in the GUI: you are asked for the two files)
#
#   atlas.json  authoritative: func symbols rename the function at addr (USER_DEFINED); table/data/struct
#               become labels. With -create, a func address without a function becomes one when it looks like
#               an entry (task entry, call target, or not inside another function); otherwise it gets a label.
#   autonames   proposals: rename only functions still carrying a default (FUN_) or analysis name, as source
#               ANALYSIS, so your own names win. Rows below -min-conf (default low = all) are skipped.
#   "Class::method" names go into a class namespace.
#
# Headless (PyGhidra): pyghidraRun -H <proj_dir> <proj> -process -noanalysis -scriptPath tools/atlas \
#                      -postScript apply_names.py docs/atlas.json docs/autonames.json -create
# Our own script (Caduceus repo, tools/atlas/). Contains no firmware code.
# @category Caduceus
# @runtime PyGhidra
import json, io

from ghidra.program.model.symbol import SourceType
from ghidra.app.util import NamespaceUtils
from ghidra.util.exception import DuplicateNameException

CONF = {'low': 0, 'medium': 1, 'high': 2}
stat = {}

def bump(k):
    stat[k] = stat.get(k, 0) + 1

def load(p):
    with io.open(p, encoding='utf-8') as f:
        return json.load(f)

def split(full):
    i = full.rfind('::')
    return (None, full) if i < 0 else (full[:i], full[i + 2:])

def namespace(path, src):
    if path is None:
        return currentProgram.getGlobalNamespace()
    return NamespaceUtils.createNamespaceHierarchy(path, None, currentProgram, src)

def addr(s):
    try:
        return toAddr(int(s, 16))
    except Exception:
        return None

def rename(f, full, src, what, force):
    if not force and src == SourceType.ANALYSIS and f.getSymbol().getSource() == SourceType.USER_DEFINED:
        bump('kept user name'); return
    ns_path, nm = split(full)
    ns = namespace(ns_path, src)
    try:
        f.getSymbol().setNameAndNamespace(nm, ns, src)
    except DuplicateNameException:
        f.getSymbol().setNameAndNamespace(nm + '_' + str(f.getEntryPoint()), ns, src)
    bump(what)

def label(ad, full, src, what):
    ns_path, nm = split(full)
    s = currentProgram.getSymbolTable().createLabel(ad, nm, namespace(ns_path, src), src)
    s.setPrimary()
    bump(what)

def looks_like_entry(ad, name, sig):
    if 'entry' in sig or name.startswith('task_'):
        return True
    for r in getReferencesTo(ad):
        if r.getReferenceType().isCall():
            return True
    return getFunctionContaining(ad) is None

def main():
    args = list(getScriptArgs())
    if not args:
        args = [askFile('atlas.json', 'Use').getPath(), askFile('autonames.json', 'Use').getPath()]
    atlas = args[0] if args else '-'
    auto = args[1] if len(args) > 1 else '-'
    opts = args[2:]
    create, comments, force = '-create' in opts, '-comments' in opts, '-force' in opts
    min_conf = CONF[opts[opts.index('-min-conf') + 1]] if '-min-conf' in opts else 0
    mem = currentProgram.getMemory()

    if atlas != '-':
        for s in load(atlas)['symbols']:
            ad = addr(s['addr'])
            name, kind = s['name'], s['kind']
            sig, notes = s.get('sig') or '', s.get('notes') or ''
            if ad is None or not mem.contains(ad):
                bump('atlas: address not in memory'); continue
            if kind == 'func':
                f = getFunctionAt(ad)
                if f is None and create and looks_like_entry(ad, name, sig):
                    if getInstructionAt(ad) is None and getInstructionContaining(ad) is None:
                        disassemble(ad)
                    f = createFunction(ad, None) if getInstructionAt(ad) is not None else None
                    bump('atlas: function created' if f is not None else 'atlas: create failed')
                if f is not None:
                    rename(f, name, SourceType.USER_DEFINED, 'atlas: function renamed', force)
                else:
                    label(ad, name, SourceType.USER_DEFINED, 'atlas: label (no function entry)')
            else:
                label(ad, name, SourceType.USER_DEFINED, 'atlas: label ' + kind)
            if comments and (sig or notes) and getPlateComment(ad) is None:
                setPlateComment(ad, 'atlas: ' + name + ('\n' + sig if sig else '') + ('\n' + notes if notes else ''))

    if auto != '-':
        for s in load(auto)['names']:
            if s['method'] == 'atlas':
                continue
            if CONF.get(s['confidence'], 0) < min_conf:
                bump('auto: below min-conf'); continue
            ad = addr(s['addr'])
            f = getFunctionAt(ad) if ad is not None else None
            if f is None:
                bump('auto: no function at addr'); continue
            src = f.getSymbol().getSource()
            if not force and src in (SourceType.USER_DEFINED, SourceType.IMPORTED):
                bump('auto: kept existing name'); continue
            rename(f, s['name'], SourceType.ANALYSIS, 'auto: renamed ' + s['method'], force)

    for k in sorted(stat):
        print('%6d  %s' % (stat[k], k))

main()
