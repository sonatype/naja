import sys
import os
import pandas as pd
import subprocess
import json
import tempfile
import signal

args = sys.argv
current_dir = os.getcwd()
test_repo_path = os.path.abspath(os.path.expanduser(args[1]))
if os.path.exists( test_repo_path) :
    repo_path = test_repo_path
else:
    repo_path = current_dir
test_rule_path = os.path.abspath(os.path.expanduser(args[2]))
fallback_path = os.path.abspath('/opt/cobra/rulerepo/')
if os.path.exists( test_rule_path ) :
    rule_repo_path = test_rule_path
elif os.path.exists( fallback_path ) :
    rule_repo_path = os.path.abspath('/opt/cobra/rulerepo/')
else:
    raise Exception("Invalid repo path")
json_path = os.path.abspath(os.path.join(rule_repo_path, 'lookup_info.json'))
if not os.path.exists(json_path):
    raise Exception("Repo path exists but is not the base directory of the repository")

def getLanguagesToRunCobraOn(repofolder):
    run_language = {"Java": False, "Python": False, "C": False, "Ada": False}
    for root, dirnames, filenames in os.walk(repofolder):
        for filename in filenames:
            if filename.endswith(".java"):
                run_language["Java"] = True
            elif filename.endswith(".py"):
                run_language["Python"] = True
            elif filename.endswith((".c", ".h")):
                run_language["C"] = True
            elif filename.endswith((".ads", ".adb")):
                run_language["Ada"] = True
    return run_language

def addRepoCobraCommands(cobra_commands, repo_path, langs_to_run, debug = False):
    cobra_path = os.path.join(repo_path, "cobra")
    if os.path.exists(cobra_path):
        for key in langs_to_run.keys():
            lang_path = os.path.join(cobra_path, key.lower())
            if os.path.exists(lang_path):
                if debug == True:
                    print("we're going to add "+key+" commands")
                for root,dirnames,filenames in os.walk(lang_path):
                    for filename in filenames:
                        cobra_commands[key].append(os.path.join(root, filename))
    return cobra_commands

def addJSONCobraCommands(cobra_commands, json_loc, rule_loc):
    ourrules = pd.read_json(json_loc)
    #should check for existence before adding
    for key in cobra_commands.keys():
        rules_per_language=list(ourrules[ourrules["Language"] == key]["FileLocation"])
        for rule in rules_per_language:
            abspath = os.path.abspath(os.path.join(rule_loc, rule))
            if os.path.exists(abspath):
                #add stuff that actually exists to our rules to run
                cobra_commands[key].append(abspath)
    return cobra_commands

def runCobraCommands(repo_path, cobra_commands, langs_to_run, lang_flags, lang_regex, debug = False):
    os.chdir(repo_path)
    cobra_file = ""
    cobra_regex = ""
    lang_flag = ""
    all_run_info = []
    commands_run = []
    for key in cobra_commands.keys():
        if langs_to_run[key]:
            expr = lang_regex[key]
            lang_flag = lang_flags[key]
            if debug == True:
                print("Running " + key+ " Cobra Commands")
                print("=====================================")
            for command in cobra_commands[key]:
                #right here I need to set up a temp file to actually run
                if command.startswith(repo_path):
                    edited_command = readAndEditCobraScript(command)
                    tmp = tempfile.NamedTemporaryFile(delete=False)
                    name = tmp.name
                    with open(tmp.name, 'w') as f:
                        for chunk in edited_command:
                            for cmd in chunk:
                                f.write(cmd+ '\n')
                    tmp.close()
                    #put this into the cobra command instead
                
                    cobra_command = ["cobra", "-json", lang_flag,
                                    "-f", name,
                                    "-recursive", expr]
                else:
                    cobra_command = ["cobra", "-json", lang_flag,
                                     "-f", command, "-recursive", expr]
                if debug:
                    print(' '.join(cobra_command))
                    print("Running file: " + command)
                run_info = subprocess.run(cobra_command, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
                if run_info.returncode != 0:
                    print('Cobra exited with non-zero return code. code =', run_info.returncode,\
                          '(segfault)' if run_info.returncode == -signal.SIGSEGV else '')
                    print('std_err:')
                    print(run_info.stderr.decode())
                if debug:
                    print('Cobra output:')
                    print(run_info.stdout.decode())
                commands_run.append(command)
                all_run_info.append(run_info)
    return all_run_info, commands_run

def findJSONSection(s):
    num_right = 0
    num_left = 0
    left_idx = -1
    right_idx = -1
    for i in range(len(s))[::-1]:
        if s[i] == ']':
            if num_right == 0:
                right_idx = i
            num_right += 1
        if s[i] == '[':
            num_left += 1

        if num_left == num_right and num_right != 0:
            left_idx = i
            outinfo = [left_idx, right_idx]
            return outinfo
            
def findJSONOutputs(s):
    start = True
    end_idx = len(s)
    json_outputs = []
    pat = findJSONSection(s[0:end_idx])
    while pat != None or start == True:
        start = False
        if s[0:end_idx].strip().endswith("pattern") or s[0:end_idx].strip().endswith("patterns"):
            pat = findJSONSection(s[0:end_idx])
            json_outputs.extend(json.loads(s[pat[0]:pat[1]+1]))
            end_idx = pat[0]-1
            if (end_idx < 0):
              break
        else:
            return json_outputs
    return json_outputs

def gatherJSON(run_info, cmds_run):
    json_outputs = {}
    for i in range(len(run_info)):
        v = run_info[i].stdout.decode().strip()
        json_outputs[cmds_run[i]] = findJSONOutputs(v)
    return json_outputs

def editCobra(cmds):
    namelist = ['sonatypePat' + str(i) for i in range(len(cmds))]
    num_patterns = len(cmds)
    display_commands = []
    for i in range(num_patterns):
        cmds[i].append('ps create '+ namelist[i])
        cmds[i].append('r')
        display_commands.append('dp '+ namelist[i])
    cmds.append(display_commands)
    return cmds
    
def cleanNewLines(s):
    #first cleanup the plaintext
    indep_patterns = s.split('\n')
    cleaned_commands = []
    for pat in indep_patterns:
        entry = pat.strip()
        if entry != '':
            cleaned_commands.append(entry)
    return cleaned_commands
    
def chunkCommands(clean_commands):
    #then chunk each one into a sequence of commands separated by a reset
    chunked_commands = [[]]
    for cmd in clean_commands:
        if cmd != 'r' and cmd != 'reset':
            chunked_commands[-1].append(cmd)
        else:
            chunked_commands.append([])
    return chunked_commands

def readAndEditCobraScript(file):
    tmp = open(file,'r')
    txt = tmp.read()
    tmp.close()
    clean_commands = cleanNewLines(txt)
    chunked_commands = chunkCommands(clean_commands)
    return editCobra(chunked_commands)

def main():
    #utils
    lang_regex = {"Java": "*.java", "C": "*.[ch]", "Python": "*.py", "Ada": ".ad[bs]"}
    lang_flags = {"Java": "-Java", "C": "", "Python": "-Python", "Ada": "-Ada"}
    cobra_to_run = {"Java": [], "Python": [], "C": [], "Ada": []}

    langs = getLanguagesToRunCobraOn(repo_path)
    cobra_to_run = addRepoCobraCommands(cobra_to_run, repo_path, langs)
    cobra_to_run = addJSONCobraCommands(cobra_to_run, json_path, rule_repo_path)
    all_run_info, commands_run = runCobraCommands(repo_path, cobra_to_run, langs, lang_flags, lang_regex, debug = True )
    collated_json = gatherJSON(all_run_info, commands_run)
    jsondump = json.dumps(collated_json)
    f = open("/tmp/tmpcobra.json",'w')
    f.write(jsondump)
    f.close()
    print(jsondump)
if __name__ == "__main__":
    main()
