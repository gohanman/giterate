#import pygit2
import re
import os,os.path
import shelve
from ConfigParser import ConfigParser
from getopt import gnu_getopt
from sys import argv, exit

# driver enum
class driver:
    GITPYTHON = 1
    PYGIT2 = 2

# globalish value specifying driver
class gitmode:
    d = None

class giterate:

    # constructor
    # @param project_name [string]
    # @param path [string] path to repo files
    # @param remote_url [string] git remote repo used for updates
    def __init__(self, project_name, path, remote_url):
        self.remote = None
        self.project = project_name
        self.my_dir = os.path.dirname(os.path.abspath(__file__))
        self.db = shelve.open(self.my_dir + os.sep + "cache.db", "c")
        self.excludes = []
        self.includes = []
        if gitmode.d == driver.GITPYTHON:
            self.repo = git.Repo(path)
            try:
                self.remote = self.repo.remotes._giterate
            except:
                self.remote = self.repo.create_remote('_giterate', remote_url)
        elif gitmode.d == driver.PYGIT2:
            self.repo = pygit2.Repository(path)
            for remote in self.repo.remotes:
                if remote.name == "_giterate":
                    self.remote = remote
                    break
            if type(self.remote) == type(None):
                self.remote = self.repo.create_remote("_giterate", remote_url)
            else:
                self.remote.url = remote_url

    def set_includes(self, i):
        if type(i) != type([]):
            raise ValueError
        self.includes = i

    def set_excludes(self, x):
        if type(x) != type([]):
            raise ValueError
        self.excludes = x
    
    def check(self):
        current = "0"
        if self.db.has_key(self.project):
            current = self.db[self.project]
        latest = self.latest_version()
        if current == latest:
            print "Up-to-date"
        elif latest == None:
            print "No releases found"
        elif current == "0" or self.version_key(current) < self.version_key(latest):
            print "Update available"
            print "Current Version: " + current
            print "Available Version: " + latest
        else:
            print "Unknown Version Installed"
            print "Current Version: " + str(current)
            print "Latest Known Version: " + latest
    
    def update(self, force=False):
        version_string = self.latest_version()
        if version_string == None:
            print "Error: no releases found"
            exit(1)
        print "Merging version " + version_string
        if gitmode.d == driver.GITPYTHON:
            tag_commit = self.repo.tag('refs/tags/' + version_string).commit
            current_id = self.repo.head.commit
            try:
                self.repo.git.merge(tag_commit)
                # check index to detect merge errors
                for stage, _ in self.repo.index.iter_blobs():
                    if stage != 0:
                        raise Exception() 
                self.db[self.project] = version_string
                print "Merge complete"
            except:
                self.repo.head.reset(commit=current_id, index=True, working_tree=True)
                print "Merge failed. Rolling back changes"
        elif gitmode.d == driver.PYGIT2:
            ref = self.repo.lookup_reference("refs/tags/" + version_string)
            current_id = self.repo.head.get_object().id
            # I believe merge will throw an exception
            # if a conflict occurs but haven't verified that
            # with a proper test case
            try:
                merge_result = self.repo.merge(ref.get_object().id)
                if not(merge_result.is_uptodate):
                    user = pygit2.Signature('giterate', 'giterate@giterate')
                    tree = self.repo.TreeBuilder().write()
                    new_oid = self.repo.create_commit(self.head.name, user, user, tree, [])
                    self.repo.head.resolve().target = new_oid
                    self.db[self.project] = version_string
                    print "Merge complete"
                elif merge_result.is_uptodate:
                    self.db[self.project] = version_string
                    print "Merge not needed; updating records"
            except:
                self.repo.reset(current_id, pygit2.GIT_RESET_HARD)
                print "Merge failed. Rolling back changes"

    # get latest version
    # returns tag string
    def latest_version(self):
        self.remote.fetch()
        matches = self.get_tags()
        for val in matches[:]:
            for x in self.excludes:
                if x in val: matches.remove(val)
            for i in self.includes:
                if i not in val: matches.remove(val)
        matches.sort(key=self.version_key)

        if len(matches) > 0:
            return matches[-1]
        else:
            return None

    def get_tags(self):
        if gitmode.d == driver.GITPYTHON:
            return [t.name for t in self.repo.tags]
        elif gitmode.d == driver.PYGIT2:
            regex = re.compile('^refs/tags/(.*)$')
            matches = [m.group(1) for m in map(regex.match, self.repo.listall_references()) if m]
            return matches
    
    # keying function to sort version strings
    # in a sensible order
    def version_key(self, version_string):
        dot_elements = ""
        build_data = ""
        if "-" in version_string:
            dot_elements, build_data = version_string.split("-", 1)

        key = []
        if "." in dot_elements:
            for elem in dot_elements.split("."):
                try:
                    key.append(int(elem))
                except:
                    key.append(elem)
        else:
            key.append(dot_elements)
        if "." in build_data:
            for elem in build_data.split("."):
                try:
                    key.append(int(elem))
                except:
                    key.append(elem)
        else:
            key.append(build_data)

        return key

    @staticmethod
    def print_help():
        this_dir = os.path.dirname(os.path.abspath(__file__))
        print 'Usage: giterate --name <project_name> [OPTIONS]'
        print ''
        print "\t-n, --name\tSpecify project name"
        print "\t-c, --config\tConfiguration file"
        print "\t\t\tDefault: /etc/giterate.conf, " + this_dir + os.sep + 'giterate.conf'
        print "\t-p, --path\tProject\'s filesystem path"
        print "\t-r, --remote\tGit URL for update repo"
        print "\t-i, --include\tOnly include tags containing this string"
        print "\t\t\tMay be specified multiple times"
        print "\t-x, --exclude\tExclude tags containing this string"
        print "\t\t\tMay be specified multiple times"
        print "\t-u, --update\tApply available updates"
        print "\t\t\tOtherwise just check for available updates"
        print "\t-f, --force\tDo not rollback on update errors"
        print "\t-s, --self\tCheck for giterate updates"
        print "\t-h, --help\tPrint this message"
        print ''
        print """A filesystem path and remote URL for the project must be supplied via
config file or as command line options"""

if __name__ == '__main__':
    try:
        import git
        gitmode.d = driver.GITPYTHON
    except:
        try:
            import pygit2
            gitmode.d = driver.PYGIT2
        except:
            print "No drivers found!"
            print "Install GitPython or pygit2"
            exit(1)

    try:
        optlist, args = gnu_getopt(argv[1:], 
                                   'n:p:r:c:uhsx:i:f', 
                                   ['name=', 'path=', 'remote=', 'config=', 'update', 'help', 'self','exclude=','include=', 'force'])
    except Exception, e:
        giterate.print_help()
        print e
        exit(1)

    name = None
    path = None
    remote = None
    update = False
    force = False
    excludes = []
    includes = []

    config = ConfigParser()
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.isfile('/etc/giterate.conf'):
        config.read('/etc/giterate.conf')
    elif os.path.isfile(this_dir + os.sep + 'giterate.conf'):
        config.read(this_dir + os.sep + 'giterate.conf')

    for k, v in optlist:
        if k in ['-n', '--name']:
            name = v
        elif k in ['-p', '--path']:
            path = v
        elif k in ['-r', '--remote']:
            remote = v
        elif k in ['-u', '--update']:
            update = True
        elif k in ['-f', '--force']:
            force = True
        elif k in ['-c', '--config']:
            if os.path.isfile(v):
                # load requested config
                config = ConfigParser()
                config.read(v)
            else:
                print 'File "' + v + '" does not exist'
                exit(1)
        elif k in ['-s', '--self']:
            name = 'giterate'
            path = this_dir
            remote = 'https://github.com/gohanman/giterate'
        elif k in ['-x', '--exclude']:
            excludes.append(v)
        elif k in ['-i', '--include']:
            includes.append(v)
        elif k in ['-h', '--help']:
            giterate.print_help()
            exit(0)

    if name == None:
        giterate.print_help()
        print 'Error: name must be specified'
        exit(1)

    g = None
    if path != None and remote != None:
        g = giterate(name, path, remote)
    else:
        if config.has_section(name):
            if not(config.has_option(name, 'path')):
                print 'Error: "path" is not specified in config file for project ' + name
                exit(1)
            elif not(config.has_option(name, 'url')):
                print 'Error: "url" is not specified in config file for project ' + name
                exit(1)
            else:
                g = giterate(name, config.get(name, 'path'), config.get(name, 'url'))
                if config.has_option(name, 'exclude'):
                    excludes += [v for v in config.get(name, 'exclude').split(' ')]
                if config.has_option(name, 'include'):
                    includes += [v for v in config.get(name, 'include').split(' ')]
        else:
            print 'Error: no config section for project ' + name
            exit(1)
    
    g.set_excludes(excludes)
    g.set_includes(includes)

    if update:
        g.update(force)
    else:
        g.check()
    exit(0)
