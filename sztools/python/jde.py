import socket
import vim
import os.path
import time
import re
import traceback
import StringIO
from xml.etree.ElementTree import ElementTree
from subprocess import Popen
from pyparsing import *
from string import Template

HOST = 'localhost'
PORT = 9527
END_TOKEN = "==end=="
MAX_CPT_COUNT = 200

class VimUtil(object):
    @staticmethod
    def inputOption(options):
        vim.command("redraw")
        for index,line in enumerate(options) :
            print " %s : %s " % (str(index), line)
        vim.command("let b:vjde_option_index = input('please enter a selection')")
        exists = vim.eval("exists('b:vjde_option_index')")
        if exists  ==  "1" :
            index = vim.eval("b:vjde_option_index")
            vim.command("unlet b:vjde_option_index")
        else :
            index = None
        return index

    @staticmethod
    def writeToJdeConsole(text):
        if not text :
            return
        vim.command("call SwitchToSzToolView('%s')" % "JdeConsole")
        if type(text) == type(""):
            lines = text.split("\n")
        else :
            lines = text
        win_height = len(lines) + 1
        win_height = 20 if win_height > 20 else win_height
        vim.command("resize %s" % str(win_height) )
        output(lines)
        listwinnr=str(vim.eval("winnr('#')"))
        vim.command("exec '%s wincmd w'" % listwinnr)

class ProjectManager(object):
    @staticmethod
    def getProjectRoot(filePath):
        projectRoot = None
        parent = filePath
        if not filePath :
            return None
        while True :
            tmpdir = os.path.dirname(parent)
            if tmpdir == "" or tmpdir == "/" or tmpdir == parent :
                break
            parent = tmpdir
            fullname = lambda name : os.path.join(parent,name)
            prj_names =[fullname(name) for name in [".project",".classpath"]]
            if os.path.exists(prj_names[0]) and os.path.exists(prj_names[1]):
                projectRoot = parent
                break
        return projectRoot

    @staticmethod
    def getSrcLocations(filePath):
        tree = ElementTree()
        classpathXml = ProjectManager.getClassPathXml(filePath)
        if os.path.isdir(classpathXml) :
            return [ classpathXml ]
        project_root = ProjectManager.getProjectRoot(filePath)
        tree.parse(classpathXml)
        entries = tree.findall("classpathentry")
        src_locs = []
        for entry in  entries :
            if entry.get("kind") == "src" :
                src_locs.append(os.path.join(project_root,entry.get("path")))
        return src_locs

    @staticmethod
    def getClassPathXml(filePath):
        projectRoot = ProjectManager.getProjectRoot(filePath)
        if not projectRoot :
            parent = os.path.dirname(filePath)
            return parent
        return os.path.join(projectRoot,".classpath")

    @staticmethod
    def getAntBuildXml(filePath):
        projectRoot = ProjectManager.getProjectRoot(filePath)
        if not projectRoot : return None
        antBuildXml = os.path.join(projectRoot,"build.xml")
        if os.path.exists(antBuildXml):
            return antBuildXml
        return None

    @staticmethod
    def projectInit():
        pwd = os.getcwd()
        projectName =  os.path.basename(os.getcwd())
        examples_dir = os.path.join(getShareHome(),"examples")
        projectInitXml = os.path.join(examples_dir,"project.xml")
        classpathInitXml = os.path.join(examples_dir,"classpath.xml")
        jdeInitXml = os.path.join(examples_dir,"jde.xml")
        if not os.path.exists("src") :
            os.mkdir("src")
        if not os.path.exists("lib") :
            os.mkdir("lib")
        if not os.path.exists("dst") :
            os.mkdir("dst")
        lines = open(projectInitXml).readlines()
        f = open(".project","w")
        for line in lines :
            line=line.replace("test",projectName)
            f.write(line)
        f.close()
        shutil.copy2(classpathInitXml, "./.classpath")
        shutil.copy2(jdeInitXml, "./.jde")
        print "project initialized in current dir succeed."

    @staticmethod
    def projectClean():
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        Talker.projectClean(classPathXml)

class Talker(object):
    @staticmethod
    def send(params):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((HOST, PORT))
        sb = []
        for item in params :
            sb.append("%s=%s\n" %(item,params[item]))
        sb.append('%s\n' % END_TOKEN)
        s.send("".join(sb))
        total_data=[]
        while True:
            data = s.recv(8192)
            if not data: break
            total_data.append(data)
        s.close()
        return ''.join(total_data)

    @staticmethod
    def getPackageList(pkgname,xmlPath):
        params = dict()
        params["cmd"]="completion"
        params["completionType"] = "package"
        params["pkgname"] = pkgname
        params["classPathXml"] = xmlPath
        data = Talker.send(params)
        return data

    @staticmethod
    def getClassList(classNameStart,xmlPath):
        params = dict()
        params["cmd"]="completion"
        params["completionType"] = "class"
        params["className"] = classNameStart
        params["classPathXml"] = xmlPath
        data = Talker.send(params)
        return data

    @staticmethod
    def doLocatedbCommand(args):
        params = dict()
        params["cmd"]="locatedb"
        params["args"] = ";".join(args)
        params["pwd"] = os.getcwd()
        data = Talker.send(params)
        return data

    @staticmethod
    def getMemberList( args ):
        params = dict()
        sourceFile ,classnameList,xmlPath,memberType,expTokens = args
        params["cmd"]="completion"
        params["sourceFile"] = sourceFile
        params["completionType"] = memberType
        params["classnames"] = ",".join(classnameList)
        params["classPathXml"] = xmlPath
        params["expTokens"] = ",".join(expTokens)
        data = Talker.send(params)
        return data

    @staticmethod
    def compileFile(xmlPath,sourceFile):
        params = dict()
        params["cmd"]="compile"
        params["classPathXml"] = xmlPath
        params["sourceFile"] = sourceFile
        data = Talker.send(params)
        return data

    @staticmethod
    def copyResource(xmlPath,sourceFile):
        params = dict()
        params["cmd"]="copyResource"
        params["classPathXml"] = xmlPath
        params["sourceFile"] = sourceFile
        data = Talker.send(params)
        return data

    @staticmethod
    def runFile(xmlPath,sourceFile):
        params = dict()
        params["cmd"]="run"
        params["classPathXml"] = xmlPath
        params["sourceFile"] = sourceFile
        data = Talker.send(params)
        return data

    @staticmethod
    def autoImport(xmlPath,varNames,pkgName):
        params = dict()
        params["cmd"]="autoimport"
        params["classPathXml"] = xmlPath
        params["varNames"] = varNames
        params["pkgName"] = pkgName
        data = Talker.send(params)
        return data

    @staticmethod
    def dumpClass(xmlPath,classnameList):
        params = dict()
        params["cmd"]="dumpClass"
        params["classPathXml"] = xmlPath
        params["dumpClassNames"] = ",".join(classnameList)
        data = Talker.send(params)
        return data

    @staticmethod
    def overideMethod(xmlPath,varNames):
        params = dict()
        params["cmd"]="overide"
        params["classPathXml"] = xmlPath
        params["varNames"] = ",".join(varNames)
        data = Talker.send(params)
        return data

    @staticmethod
    def fetchResult(guid):
        params = dict()
        params["cmd"]="fetchResult"
        params["jobId"] = guid
        data = Talker.send(params)
        return data

    @staticmethod
    def runAntBuild(vimServer,cmdName,runInShell):
        params = dict()
        params["cmd"]="runSys"
        params["vimServer"] = vimServer
        params["cmdName"] = cmdName
        params["runInShell"] = runInShell
        data = Talker.send(params)
        return data

    @staticmethod
    def hotswapEnabled(enabled,port=None):
        params = dict()
        params["cmd"]="setHotswap"
        params["hotSwapEnabled"] = enabled
        if enabled == "true" and port != None :
            params["hotSwapPort"] = port
        data = Talker.send(params)
        return data

    @staticmethod
    def projectClean(xmlPath):
        params = dict()
        params["cmd"]="projectClean"
        params["classPathXml"] = xmlPath
        data = Talker.send(params)
        return data


class EditUtil(object):

    @staticmethod
    def createSkeleton():
        vim_buffer = vim.current.buffer
        cur_file = vim_buffer.name
        cur_path = os.path.dirname(cur_file)
        prj_root = ProjectManager.getProjectRoot(cur_file)
        src_locs = ProjectManager.getSrcLocations(cur_file)
        pkg = ""
        for src_loc in src_locs :
            abs_src = os.path.join(prj_root, src_loc)
            if cur_path.startswith(abs_src) :
                pkg = cur_path[ len(abs_src)+1 : ]
        if pkg != "" :
            vim_buffer.append("package %s;" % pkg.replace(os.path.sep,"."))
            vim_buffer.append("")

        class_name = os.path.splitext(os.path.basename(cur_file))[0]
        s = Template("public class $name {\n\n}")
        skeleton = s.substitute(name=class_name)
        for line in skeleton.split("\n"):
            vim_buffer.append(line)
        del vim_buffer[0]

    @staticmethod
    def generateGseter():
        jdef_parser = Parser.getJavaVarDefParser(None,False)
        statement = OneOrMore(Group(jdef_parser))
        statement.ignore( javaStyleComment )
        startCol,endCol,startLine,endLine=getVisualArea()
        vim_buffer = vim.current.buffer
        selectedText = "\n".join(vim_buffer[startLine-1:endLine])
        results = statement.parseString(selectedText)

        template = """
          public void set$1($2 $3) {
            this.$3=$3;
          }
          public $2 get$1() {
            return this.$3;
          }
          """

        sb = []
        for item in  results :
            tmp = []
            for type_token in item[0]:
                if type_token not in "<>[]"  :
                    if len(tmp) > 0 and tmp[-1] not in "<>[]":
                        tmp.append(",")
                tmp.append(type_token)
            vartype = "".join(tmp)
            varname = item[1]
            result = template.replace("$1",varname.title())
            result = result.replace("$2",vartype)
            result = result.replace("$3",varname)
            sb.append(result)
        if sb == [] :
            return
        endline = Parser.parseClassEnd()
        del vim_buffer[endline]
        output(sb,append=True)
        output("}",append=True)
        #format the getter,setter code
        vim.command("normal %sGV200j=" % endline)

    @staticmethod
    def overideMethod():
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml : return
        allFullClassNames = Parser.getAllSuperClassFullNames()
        resultText = Talker.overideMethod(classPathXml,allFullClassNames)
        VimUtil.writeToJdeConsole(resultText)

    @staticmethod
    def gotoDefinition():
        (row,col) = vim.current.window.cursor
        vim_buffer = vim.current.buffer
        line = vim_buffer[row-1]
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        dotExpParser = Parser.getJavaDotExpParser()
        tokenEndCol = col
        for char in line[col:] :
            if not re.match("\w",char) :
                break
            tokenEndCol += 1
        expTokens = dotExpParser.searchString(line[0:tokenEndCol])[0]
        varName = expTokens[0]
        memberName = expTokens[-1]

        if varName[0].isupper():
            classname = varName
        else :
            classname = Parser.getVarType(varName,row-1)
            if not classname :
                classname = varName
        classNameList = Parser.getFullClassNames(classname)
        # find exact match bin classname
        abs_path = "abs"
        has_match = False
        if len(classNameList) == 1 :
            rlt_path = classNameList[0].replace(".", os.path.sep)+".java"
            src_locs = ProjectManager.getSrcLocations(current_file_name)
            for src_loc in src_locs :
                abs_path = os.path.join(src_loc, rlt_path)
                if os.path.exists(abs_path) :
                    has_match = True
                    break
                    #vim.command("edit %s" % abs_path)
        if has_match :
            matched_row = 0
            lines = open(abs_path,"r").readlines()
            members = Parser.parseAllMemberInfo(lines)
            for name,mtype,rtntype,param,lineNum in members :
                if name == memberName :
                    matched_row = lineNum
            vim.command("edit %s" % abs_path)
            vim.command("normal %sG" % str(matched_row))
        return

    @staticmethod
    def dumpClassInfo():
        classname = vim.eval("expand('<cword>')")
        if classname == "" : return
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml : return
        classNameList = Parser.getFullClassNames(classname)
        result = Talker.dumpClass(classPathXml,classNameList)
        VimUtil.writeToJdeConsole(result)

class Compiler(object):

    @staticmethod
    def displayMsg():
        allErrorMsg = globals().get("allErrorMsg")
        if allErrorMsg == None :
            return 
        vim_buffer = vim.current.buffer
        bufErrorMsg = allErrorMsg.get(vim_buffer.name)
        if bufErrorMsg == None : 
            return
        (row,col) = vim.current.window.cursor
        errorText = bufErrorMsg.get(str(row))
        if errorText == None :
            return
        vim.command("call DisplayMsg('%s')" % errorText)

    @staticmethod
    def highlightErrorGroup(errorRow,start,end,errorType):
        if errorType == "W" :
            group = "SzjdeWarning"
        else :
            group = "SzjdeError"

        errorRow,start,end = int(errorRow), int(start), int(end)
        vim_buffer = vim.current.buffer
        charCount = 0
        fileformat = vim.eval("&fileformat")
        newLineCount =1 
        if fileformat == "dos" :
            newLineCount = 2

        for row in vim_buffer[0:errorRow-1] :
            charCount += len(unicode(row)) +  newLineCount
        rowStart = 0 if start - charCount < 0 else start - charCount
        rowEnd = end - charCount + 3
        if rowEnd < 0 :
            rowEnd = rowStart + len(unicode(vim_buffer[errorRow]))  
        signcmd=Template("sign place ${id} line=${lnum} name=${name} buffer=${nr}")
        bufnr=str(vim.eval("bufnr('%')"))
        signcmd =signcmd.substitute(id=errorRow,lnum=errorRow,name=group, nr=bufnr)
        syncmd = """syn match %s "\%%%sl\%%>%sc.\%%<%sc" """ %(group, errorRow, rowStart, rowEnd)
        vim.command(syncmd)
        vim.command(signcmd)

    @staticmethod
    def compileCurrentFile():
        (row,col) = vim.current.window.cursor
        vim_buffer = vim.current.buffer

        line = vim_buffer[row-1]
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml :
            return
        resultText = Talker.compileFile(classPathXml,current_file_name)
        errorMsgList = resultText.split("\n")
        hasError = False
        qflist = []
        vim.command("highlight link SzjdeError SpellBad")
        vim.command("highlight link SzjdeWarning SpellLocal")
        vim.command("sign define SzjdeError text=>> texthl=ErrorMsg")
        vim.command("sign define SzjdeWarning text=>> texthl=TODO")
        vim.command("syntax clear SzjdeError")
        vim.command("syntax clear SzjdeWarning")
        vim.command("sign unplace *")
        global allErrorMsg 
        allErrorMsg = {}
        bufErrorMsg = {} 
        for line in errorMsgList:
            if line.strip() == "" : continue
            try :
                errorType,filename,lnum,text,lstart,lend = line.split("::")
                bufErrorMsg[lnum]=text
                bufnr=str(vim.eval("bufnr('%')"))
                Compiler.highlightErrorGroup(lnum,lstart,lend,errorType)
                qfitem = dict(bufnr=bufnr,lnum=lnum,text=text,type=errorType)
                qflist.append(qfitem)
            except Exception , e:
                fp = StringIO.StringIO()
                traceback.print_exc(file=fp)
                message = fp.getvalue()
                logging.debug(message)
        allErrorMsg[current_file_name] = bufErrorMsg

        vim.command("call setqflist(%s)" % qflist)
        """
        if len(errorMsgList) > 0 :
            vim.command("cw")
            listwinnr=str(vim.eval("winnr('#')"))
            vim.command("exec '%s wincmd w'" % listwinnr)
        if len(qflist) > 0 :
            vim.command("cfirst")
        """

    @staticmethod
    def copyResource():
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        if not current_file_name : return
        if current_file_name.endswith(".java") : return
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml : return
        resultText = Talker.copyResource(classPathXml,current_file_name)
        VimUtil.writeToJdeConsole(resultText)

class Runner(object):

    @staticmethod
    def runCurrentFile():
        (row,col) = vim.current.window.cursor
        vim_buffer = vim.current.buffer
        line = vim_buffer[row-1]
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml : return
        resultText = Talker.runFile(classPathXml,current_file_name)
        VimUtil.writeToJdeConsole(resultText)

    @staticmethod
    def runAntBuild(target=None):
        serverName = vim.eval("v:servername")
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        antBuildXml = ProjectManager.getAntBuildXml(current_file_name)
        if antBuildXml :
            cmdName = "ant -file "+antBuildXml
            runInShell = "false"
            if os.name == "nt" :
                runInShell = "true"
            resultText = Talker.runAntBuild(serverName,cmdName,runInShell)
        else :
            print "can't find the build.xml."

    @staticmethod
    def fetchResult(guid):
        resultText = Talker.fetchResult(guid)
        lines = resultText.split("\n")
        VimUtil.writeToJdeConsole(lines)

class AutoImport(object):

    @staticmethod
    def getImportInsertLocation():
        vim_buffer = vim.current.buffer
        pkgLocation = 0
        impLocation = -1

        for index,line in enumerate(vim_buffer):
            if line.strip().startswith("import "):
                impLocation = index
                break
        if impLocation > -1 :
            return impLocation

        for index,line in enumerate(vim_buffer):
            if line.strip().startswith("package") :
                pkgLocation = index + 1
                break
        return pkgLocation

    @staticmethod
    def addImportDef(line):
        if line.strip() == "" : return
        vim_buffer_text ="\n".join(vim.current.buffer)
        tmpDefs = line[:-1].split(";")
        hadImported = False

        for tmpDef in tmpDefs :
            pat = r"import\s+%s\b|import\s+%s" % (tmpDef, tmpDef[0:tmpDef.rfind(".")]+"\.\*")
            if re.search(pat,vim_buffer_text) :
                hadImported = True
                break
        if not hadImported :
            location = AutoImport.getImportInsertLocation()
            if ( len(tmpDefs) == 1 ) :
                insertText = "import %s;" % tmpDefs[0]
                vim.command("call append(%s,'%s')" %(str(location),insertText))
            else :
                selectedIndex = VimUtil.inputOption(tmpDefs)
                if (selectedIndex) :
                    insertText = "import %s;" % tmpDefs[int(selectedIndex)]
                    vim.command("call append(%s,'%s')" %(str(location),insertText))

    @staticmethod
    def autoImportVar():
        vim_buffer = vim.current.buffer
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml : return

        currentPackage = Parser.getPackage()
        if not currentPackage :
            currentPackage = ""

        searchText = "\n".join(vim_buffer)
        #remove comments
        commentPat = re.compile(r"(\/\*.*?\*\/)|((\/\/.*?)(?=\n))", re.DOTALL)
        searchText = commentPat.sub("",searchText)

        # upercase words except preceded by "."
        classNamePat = re.compile(r"\b(?<!\.)[A-Z]\w+\b")
        var_type_set=set(classNamePat.findall(searchText))

        varNames=",".join(var_type_set)
        resultText = Talker.autoImport(classPathXml,varNames,currentPackage)
        lines = resultText.split("\n")
        for line in lines :
            AutoImport.addImportDef(line)
        location = AutoImport.getImportInsertLocation()
        if location > 0 and vim_buffer[location-1].strip() != "" :
            vim.command("call append(%s,'')" %(str(location)))

class Parser(object):

    @staticmethod
    def parseClassEnd():
        vim_buffer = vim.current.buffer
        row_count = len(vim_buffer)
        end_line = 0
        for lineNum in range(row_count-1,-1,-1):
            line = vim_buffer[lineNum]
            if line.endswith("}") :
                end_line = lineNum
                break
        return end_line

    @staticmethod
    def parseAllMemberInfo(lines):
        memberInfo = []
        scopeCount = 0
        methodPat = re.compile(r"(?P<rtntype>[\w<>,]+)\s+(?P<name>\w+)\s*\((?P<param>.*\))")
        assignPat = re.compile("(?P<rtntype>[\w<>,]+)\s+(?P<name>\w+)\s*=")
        defPat = re.compile("(?P<rtntype>[\w<>,]+)\s+(?P<name>\w+)\s*;")
        for lineNum,line in enumerate(lines) :
            if scopeCount == 1 :
                fullDeclLine = line
                if "=" in line :
                    pat = assignPat
                    mtype = "field"
                elif "(" in line :
                    startLine = lineNum + 1
                    while True :
                        if ")" in fullDeclLine :
                            break
                        fullDeclLine = fullDeclLine +lines[startLine]
                        startLine = startLine + 1
                    pat = methodPat
                    mtype = "method"
                else :
                    pat = defPat
                    mtype = "field"
                search_res=pat.search(fullDeclLine)
                if search_res :
                    name = search_res.group("name")
                    rtntype = search_res.group("rtntype")
                    if mtype == "method" :
                        param = search_res.group("param")
                    else :
                        param = ""
                    memberInfo.append((name,mtype,rtntype,param,lineNum+1))
            if "{" in line :
                scopeCount = scopeCount + 1
            if "}" in lines[lineNum] :
                scopeCount = scopeCount - 1
        return  memberInfo

    @staticmethod
    def isJavaKeyword(word):
        keyword_str = """
            abstract    default    if            private      this
            boolean     do         implements    protected    throw
            break       double     import        public       throws
            byte        else       instanceof    return       transient
            case        extends    int           short        try
            catch       final      interface     static       void
            char        finally    long          strictfp     volatile
            class       float      native        super        while
            const       for        new           switch
            continue    goto       package       synchronized """
        match=re.search(r"\b%s\b" % word ,keyword_str)
        if match :
            return True
        return False

    @staticmethod
    def getVisibleRowNum(cursorRow):
        vim_buffer = vim.current.buffer
        scopeCount = 0
        scopeUnvisible = False
        visibleRowNum = []
        for lineNum in range(cursorRow,-1,-1):
            if "}" in vim_buffer[lineNum] :
                scopeCount = scopeCount - 1
                scopeUnvisible = True
            if "{" in vim_buffer[lineNum] and scopeUnvisible :
                scopeCount = scopeCount + 1
                if (scopeCount > -1 ) :
                    scopeUnvisible = False
                continue
            if not scopeUnvisible :
                visibleRowNum.append(lineNum)
        return visibleRowNum

    @staticmethod
    def getJavaVarDefParser(var_name=None,suppress=True):
        modifier_token = Suppress(Optional(oneOf("public private protected" )))
        storage_token = Suppress(Optional(OneOrMore(oneOf("static transient volatile final"))))
        var_type = Forward()
        if suppress :
            generic_def = Suppress("<")+delimitedList(var_type) + Suppress(">")
            array_def = Suppress("[") + Suppress("]")
        else :
            generic_def = ("<")+delimitedList(var_type) + (">")
            array_def = ("[") + ("]")
        var_type << Word(alphas,alphanums) + Optional(generic_def | array_def )
        if not var_name :
            var_name = Word( alphas, alphanums ).setResultsName("var_name")
        else :
            var_name = Keyword(var_name).setResultsName("var_name")
        statement = modifier_token + storage_token + Group(var_type) + var_name + restOfLine
        return statement

    @staticmethod
    def getJavaDotExpParser():
        java_exp = Forward()
        param_atom = java_exp | Optional('"')+Word(alphanums)+Optional('"')  
        func_param = "("+Suppress(Optional(delimitedList(param_atom))) + ")"
        atom_exp =  Combine(Word(alphas,alphanums) + Optional(func_param))
        java_exp << atom_exp + Optional(OneOrMore("." + atom_exp))
        comp_exp = java_exp + Optional(".") +  lineEnd
        return comp_exp

    @staticmethod
    def getVarType(varName,cursorRow):
        vim_buffer = vim.current.buffer
        jdef_parser = Parser.getJavaVarDefParser(varName)
        visibleRowNum = Parser.getVisibleRowNum(cursorRow)
        var_type = None
        searchLines = []
        found = False
        for row in visibleRowNum:
            lineText = vim_buffer[row].strip()
            if lineText.startswith("*") or lineText.startswith("//") :
                continue
            if varName not in lineText :
                continue
            for result in jdef_parser.searchString(vim_buffer[row]):
                if Parser.isJavaKeyword(result[0][0]) : continue
                var_type = result[0][0]
                found = True
                break
            if found : break

        return var_type

    @staticmethod
    def getFullClassNames(classname):
        vim_buffer = vim.current.buffer
        binNames = []
        currentPackage = Parser.getPackage()
        if not classname :
            return []
        if not currentPackage :
            currentPackage = ""
        hasExactMatch = False
        for line in vim_buffer:
            line = line.strip()
            if line.startswith("import "):
                lastName=line[7:-1].split(".")[-1]
                if lastName == classname :
                    binNames = [ line[7:-1] ]
                    hasExactMatch = True
                    break
                elif lastName == "*" :
                    binNames.append(line[7:-1])
        if hasExactMatch :
            return binNames
        samePkgClass=currentPackage+"."+classname
        if len(binNames) > 0 :
            binNames= [name.replace("*",classname) for name in binNames]
            binNames.append(samePkgClass)
            binNames.append(classname)
            return binNames
        else :
            return [classname,samePkgClass]


    @staticmethod
    def searchPattern(pat,groupName):
        vim_buffer = vim.current.buffer
        search_text = "\n".join(vim_buffer)
        result  = pat.search(search_text)
        if result :
            return result.group(groupName)
        return None

    @staticmethod
    def getSuperClass():
        extPat = re.compile("\s+extends\s+(?P<superclass>\w+)")
        return  Parser.searchPattern(extPat,"superclass")

    @staticmethod
    def getAllNewedClasses():
        pat = re.compile("\W+new\s+(?P<newclass>\w+)")
        vim_buffer = vim.current.buffer
        search_text = "\n".join(vim_buffer)
        result  = pat.findall(search_text)
        return result

    @staticmethod
    def getPackage():
        pkgPat = re.compile("\s*package\s+(?P<package>[\w.]+)\s*;")
        return  Parser.searchPattern(pkgPat,"package")

    @staticmethod
    def getInterfaces():
        impPat = re.compile("\s+implements\s+(?P<interface>[\w, ]+)")
        result = Parser.searchPattern(impPat , "interface")
        if result :
             return [item.strip() for item in result.split(",")]
        return None

    @staticmethod
    def getAllSuperClassFullNames():
        allSuper = Parser.getInterfaces()
        if not allSuper :
            allSuper = []
        superClass = Parser.getSuperClass()
        if superClass :
            allSuper.append(superClass)
        allFullClassNames = []
        for name in allSuper :
            classNameList = Parser.getFullClassNames(name)
            for fullName in classNameList :
                allFullClassNames.append(fullName)
        return allFullClassNames

class SzJdeCompletion(object):
    @staticmethod
    def completion(findstart,base):
        if str(findstart) == "1":
            (row,col) = vim.current.window.cursor
            line = vim.current.buffer[row-1]
            index = 0
            for i in range(col-1,-1, -1):
                char = line[i]
                if char in " =;,.'()" :
                    index = i + 1
                    break
            cmd = "let g:SzJdeCompletionIndex = %s" %str(index)
        else:
            try :
                result = SzJdeCompletion.getCompleteResult(base)
            except Exception , e :
                fp = StringIO.StringIO()
                traceback.print_exc(file=fp)
                message = fp.getvalue()
                logging.debug(message)
                result = []
            cmd = "let g:SzJdeCompletionResult = %s" % result
        vim.command(cmd)

    @staticmethod
    def getCompleteType(line):
        importExp = re.compile(r'\s*import\s+.*')
        #memberExp = re.compile(r'.*\s+\w+\.\w*$')
        omniType = None
        if importExp.match(line):
            omniType = "package"
        else :
            dotExpParser = Parser.getJavaDotExpParser()
            result = dotExpParser.searchString(line)
            omniType = "word"
            if len(result) > 0 and len(result[0]) > 1 :
                if result[0][-1] == "." or result[0][-2] == "." :
                    omniType = "member"
        return omniType

    @staticmethod
    def filterList(srcList,exp):
        exp = exp.upper()
        if exp.find("*") > -1 :
            pat = re.compile("^%s$" % exp.replace("*",".*"))
        else:
            pat = re.compile("^%s.*" %exp)

        result = [str(item) for item in srcList if pat.match(item.upper())]
        return result

    @staticmethod
    def getContextName(line):
        context = line[line.rfind(" ")+1:]
        if context.endswith(".") :
            name = context[0:-1]
        else :
            name = context[0: context.rfind(".")]
        return name

    @staticmethod
    def getWordCompleteResult(base):
        (row,col) = vim.current.window.cursor
        visibleRowNum = Parser.getVisibleRowNum(row-1)
        vim_buffer = vim.current.buffer
        bufferText = "\n".join([vim_buffer[row] for row in visibleRowNum])
        #bufferText = "\n".join([line for line in vim.current.buffer])

        pattern = r"\b%s\w*\b" % base.replace("*","\w*")
        matches = re.findall(pattern,bufferText)
        if not matches :
            matches = re.findall(pattern,bufferText,re.IGNORECASE)
        completeList = []
        if matches :
            for item in matches :
                if item not in completeList :
                    completeList.append(item)
        return completeList

    @staticmethod
    def getMemberCompleteResult(completionType,base):
        (row,col) = vim.current.window.cursor
        vim_buffer = vim.current.buffer
        line = vim_buffer[row-1]
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)

        dotExpParser = Parser.getJavaDotExpParser()
        expTokens = dotExpParser.searchString(line[0:col])[0]
        varName = expTokens[0]
        superClass = Parser.getSuperClass()
        # expTokens not include base and type
        if expTokens[-1] != "." :
            expTokens = expTokens[1:-1]
        else :
            expTokens = expTokens[1:]

        pat = re.compile("^%s.*" % base.replace("*",".*"), re.IGNORECASE)
        #pat = re.compile("^%s.*" %base, re.IGNORECASE)
        result = []


        if varName[0].isupper():
            classname = varName
            completionType = "classmember"
        elif varName == "super" :
            classname = superClass
            completionType = "inheritmember"
        elif varName == "this" :
            classname = "this"
            completionType = "inheritmember"
        else :
            classname = Parser.getVarType(varName,row-1)
            completionType = "objectmember"

        if not classname :
            if not superClass : return []
            expTokens.insert(0,varName)
            classname = superClass
            completionType = "inheritmember"

        classNameList = Parser.getFullClassNames(classname)
        params =(current_file_name,classNameList,classPathXml,completionType,expTokens)
        memberInfos = Talker.getMemberList(params).split("\n")
        result = SzJdeCompletion.buildCptDictArrary(memberInfos, pat)

        if varName == "this" and len(expTokens) < 2 :
            members = Parser.parseAllMemberInfo(vim_buffer)
            for mname,mtype,rtntype,param,lineNum in members :
                if not pat.match(mname): continue
                menu = dict()
                menu["menu"] = rtntype
                menu["icase"] = "1"
                menu["kind"] = SzJdeCompletion.getMemberTypeAbbr(mtype)
                if mtype == "method" :
                    menu["word"] = mname + "("
                    menu["menu"] = "%s %s(%s)" % (rtntype, mname,param)
                else :
                    menu["word"] = mname
                    menu["menu"] = rtntype
                result.append(menu)
        return result


    @staticmethod
    def buildCptDictArrary(memberInfos,pat):
        result = []
        for memberInfo in memberInfos :
            if memberInfo == "" : continue
            mtype,mname,mparams,mreturntype,mexceptions = memberInfo.split(":")
            if not pat.match(mname): continue
            menu = dict()
            menu["icase"] = "1"
            menu["dup"] = "1"
            menu["kind"] = SzJdeCompletion.getMemberTypeAbbr(mtype)
            if mtype == "method" :
                menu["word"] = mname + "("
                menu["menu"] = "%s %s(%s)" % (mreturntype, mname,mparams)
            else :
                menu["word"] = mname
                menu["menu"] = mreturntype
            result.append(menu)
        return result

    @staticmethod
    def getMemberTypeAbbr(mtype):
        if mtype=="method":
            return "f"
        if mtype=="field":
            return "v"
        if mtype=="constructor":
            return "d"
        return "x"

    @staticmethod
    def getCompleteResult(base):
        (row,col) = vim.current.window.cursor
        vim_buffer = vim.current.buffer
        line = vim_buffer[row-1]
        current_file_name = vim_buffer.name
        classPathXml = ProjectManager.getClassPathXml(current_file_name)
        if not classPathXml :
            return str([])
        completionType = SzJdeCompletion.getCompleteType(line[0:col])
        result = []
        if completionType == "package" :
            pkgname = SzJdeCompletion.getContextName(line)
            names = Talker.getPackageList(pkgname,classPathXml).split("\n")
            result = SzJdeCompletion.filterList(names,base)
        elif completionType == "member" :
            result = SzJdeCompletion.getMemberCompleteResult(completionType,base)
        elif completionType == "word" :
            if base[0].isupper():
                result = SzJdeCompletion.getWordCompleteResult(base)
                if result == [] :
                    classNameList = Talker.getClassList(base,classPathXml).split("\n")
                    for className in classNameList :
                        menu = dict()
                        menu["kind"] = "c"
                        menu["dup"] = "1"
                        menu["word"] = className[ className.rfind(".") + 1 : ]
                        menu["menu"] = className
                        result.append(menu)
            else :
                result = SzJdeCompletion.getWordCompleteResult(base)

        if len(result) > MAX_CPT_COUNT :
            result = result[0:MAX_CPT_COUNT]
        return str(result)

