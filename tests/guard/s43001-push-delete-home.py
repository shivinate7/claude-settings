# section 43001
FAMILY = "push-delete"
#
# The session's own home directory written out as a literal path. `rm -rf $HOME` and `rm -rf ~` deny,
# so the same folder written in full must deny too, with a trailing slash or a glob under it. The path
# is read from the runner's home, so the cases hold on any machine. A folder under the home, and another
# user's home, are not this rule's target and stay outside these cases.

HOME_LIT = os.path.expanduser("~")

for _name, _command in (
    ("the home directory as its literal path", "rm -rf " + slash(HOME_LIT)),
    ("the home directory's literal path with a trailing slash", "rm -rf " + slash(HOME_LIT) + "/"),
    ("everything under the home directory's literal path", "rm -rf " + slash(HOME_LIT) + "/*"),
    ("the home directory's literal path in double quotes", 'rm -rf "' + slash(HOME_LIT) + '"'),
):
    sh("home-literal: delete: " + _name + " denies", _command, "deny", "destructive-delete", cwd=NOGIT)

# Control: a named folder under the home is not the home, so it stays allowed.
sh("home-literal: delete: a named folder under the home directory's literal path is allowed",
   "rm -rf " + slash(os.path.join(HOME_LIT, "build", "out")), "allow", cwd=NOGIT)

# The Windows spelling of the same folder. Only a Windows run can read a Windows home, so off Windows
# the case is shown as a SKIP, never a PASS.
if os.name == "nt":
    sh("home-literal: delete: rd /s /q at the home directory's literal path denies",
       "rd /s /q " + HOME_LIT, "deny", "destructive-delete", cwd=NOGIT)
else:
    skip_case("home-literal: delete: rd /s /q at the home directory's literal path denies",
              "a Windows home folder: this run is not on Windows, so it cannot read one")
