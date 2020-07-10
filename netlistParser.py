# -*- coding: latin-1 -*-
# PART 1. The Lexer
import json
import pprint
import argparse
import gc
import sys
import time

class LispParse():
    def __init__(self):
        self.symbols = None
        self.symbolsIndex = 0
    
    def read(self,inputfd):
        inputfd = self.reduceStrings(inputfd)
        self.symbols = re.findall(r'[\w./0-9:~$]+|[()]', inputfd)
        self.symbolsIndex = 0
        self.symbolCount = len(self.symbols)

    def reduceStrings(self, inputfd):
        import re
        strings = re.findall(r'"[^"]*"', inputfd)
        self.strList = {}
        index = 0
        for strg in strings:
            r = (r'$_LP_' + str(index))
            #print(strg, r)
            #inputfd = re.sub(strg, r, inputfd)
            inputfd = inputfd.replace(strg, r)
            self.strList[r] = strg[1:-1]
            index+=1
        #print(inputfd)
        return inputfd

    def replaceString(self, strg):
        for label in self.strList:
            if strg == label:
                strg = self.strList[label]
                break
        return strg

    def expandString(self, tree):
        if type(tree) == dict:
            for key in tree:
                nkey = self.replaceString(key)
                e = tree[key]
                ne = self.replaceString(e) if type(e) == str else self.expandString(e)
                tree[nkey] = ne
        elif type(tree) == list:
            nlist = []
            for key in tree:
                if key == r'_LP_MERGE': continue
                ne = self.replaceString(key) if type(key) == str else self.expandString(key)
                nlist.append(ne)
            return nlist
        else:
            print("Error: segment not managed: "+str(tree))
        return tree

    def getsym(self):
        return self.symbols[self.symbolsIndex] if self.symbols and self.symbolsIndex < self.symbolCount else None
    
    def popsym(self):
        self.symbolsIndex+=1
        return self.symbols[self.symbolsIndex-1]
        #return self.symbols.pop(0)
    
    # PART 2. The Parser
    # Built upon the following grammar:
    #  
    #     program = expr*
    #     expr    = '(' func args ')'
    #     func    = AND|OR|NOT
    #     args    = arg*
    #     arg     = string|expr
    #     string  = [a..z]
    
    def program(self):
        r = []
        while self.getsym():
            r.append(self.expr())
        return r
    
    def expr(self):
        self.popsym() # (
        f = self.func()
        a = self.args()
        self.popsym() # )
        return {f: a}
    
    def func(self):
        return self.popsym()
    
    def args(self):
        r = []
        d = {}
        s = self.getsym()
        while s != ')':
            a = self.arg()
            if type(a) == str:
                r.append(a)
            else:
                #print("Append: {0} in {1}".format(a, d))
                for e in a.keys():
                    if e in d:
                        prev = d[e]
                        if type(prev) == list and prev[0] == '_LP_MERGE':
                            d[e].append(a[e])
                        else:
                            d[e] = [ '_LP_MERGE', prev, a[e] ]
                    else:
                        d[e] = a[e]
            s = self.getsym()
        #print("Parse: {0} and {1}".format(r, d))
        if len(r) == 0: r = d
        else:
            for e in d:
                r.append({e: d[e]})
            if len(r) == 1:
                r = r[0]
        return r
    
    def arg(self):
        if self.getsym() == '(':
            return self.expr()
        return self.string()
    
    def string(self):
        return self.popsym()
    
    # TEST = Lexer + Parser
    
    def parse(self,inputlisp):
        self.read(inputlisp)
        gc.disable()
        r = self.program()
        r = self.expandString(r)
        gc.enable()
        return r

    pass


import re
class NetParse(LispParse):
    CATHODE_PIN = 1
    ANODE_PIN = 2
    NLre = re.compile(r'^/NL([0-9]+)$')
    LEDre = re.compile(r'^D([0-9]+)$')
    RESre = re.compile(r'^R([0-9]+)$')
    
    def __init__(self, filename):
        super(type(self), self).__init__()
        self.filename = filename
        fd = open(self.filename,r'r')
        code = fd.read()
        fd.close()
        self.netlist = self.parse(code)[0]
        self.leds = []
        self.extractMembers()

    def extractMembers(self):
        self.description = {}
        self.description[r'version'] = self.netlist[r'export'][r'version']
        self.description[r'design'] = self.netlist[r'export']['design']
        self.components = self.netlist[r'export']['components']
        self.libparts = self.netlist[r'export']['libparts']
        self.libraries = self.netlist[r'export']['libraries']
        self.nets = self.netlist[r'export']['nets']

    @staticmethod
    def getLed(ref):
        m = NetParse.LEDre.match(ref)
        return None if m == None else int(m.group(1))
    @staticmethod
    def getResistor(ref):
        m = NetParse.RESre.match(ref)
        return None if m == None else m.group(1)

    def analyseSegment(self, segment, id):
        #global PP
        resitors = []
        ledAnode = []
        ledCathode = []
        maxLed = 0
        #PP.pprint(segment['node'])
        for link in segment['node']:
            ref = link['ref']
            pin = int(link['pin'])
            led = self.getLed(ref)
            if led != None:
                maxLed = max(maxLed, int(led))
                if   pin == self.ANODE_PIN:   ledAnode.append(led)
                elif pin == self.CATHODE_PIN: ledCathode.append(led)
            else:
                res = self.getResistor(ref)
                if res != None: resitors.append(res)
                else: print("Unknown component: {0} in {1}".format(link, id))
        #PP.pprint({ 'r': resitors, 'a':ledAnode, 'c':ledCathode })
        if len(resitors) != 1:
            print("Shall have a single resistor connected: {0} in {1}".format(resitors, id))
            return
        if len(ledAnode) < 1:
            print("Shall have at least one led connected by the anode: {0} in {1}".format(ledAnode, id))
            return
        if len(ledCathode) < 1:
            print("Shall have at least one led connected by the cathode: {0} in {1}".format(ledCathode, id))
            return
        r = int(resitors[0])
        while len(self.leds) < maxLed: self.leds.append({ 'led': len(self.leds) + 1 })
        for a in ledAnode:
            self.leds[a-1]['an']=r
        for c in ledCathode:
            self.leds[c-1]['ca']=r

    def findNL(self):
        global PP
        #PP.pprint(self.description);
        for segment in self.nets['net']:
            name = segment[r'name']
            mname = self.NLre.match(name) if type(name) == str else None
            if mname != None:
                self.analyseSegment(segment, mname.group(1))
        #PP.pprint(self.leds)

    def analyse(self):
        self.findNL()

    def generateTable(self):
        global PP
        max_x = 0
        max_y = 0
        min_x = 1000
        min_y = 1000
        #print(str(self.leds))
        for led in self.leds:
            x = led['x']
            y = led['y']
            if x > max_x: max_x = x
            if y > max_y: max_y = y
            if x < min_x: min_x = x
            if y < min_y: min_y = y
        print("Segment set in [%g:%g][%g:%g]" % (min_x, min_y, max_x, max_y))
        self.lines = 32
        self.columns = 32
        # Cut in 18 lines and 18 columns
        delta_x = ( max_x - min_x ) / self.lines
        delta_y = ( max_y - min_y ) / self.columns
        for led in self.leds:
            led['px'] = int((led['x'] - min_x) / delta_x)
            led['py'] = int((led['y'] - min_y) / delta_y)
        #self.leds = sorted( self.leds, key = lambda d: (d['py'], d['px'])  )
        self.leds = sorted( self.leds, key = lambda d: d['led'])
        #PP.pprint(self.leds)
        fd = open("netlist.h","w+");
        fd.write(
            " /* Hotel Pasteur PCB Table  */\n"+
            " /* File generated by {0} the {1} */\n\n".format(sys.argv[0], time.asctime(time.localtime()))+
            "static uint8_t  g_ledTableSize = {};\n".format(len(self.leds))+
            "static uint8_t  g_ledTable[{0}][{1}] = {{\n".format(len(self.leds)+1, 5)+
            "                                     /* { <led>, <ypos>, <xpos>, <anode>, <cathode>  */\n"
        )
        for led in self.leds:
            fd.write("                                        {{ {0:^5}, {1:^6}, {2:^6}, {3:^7}, {4:^7} }},\n".format(
                led['led'], led['py'], led['px'], led['an'], led['ca']))
        fd.write(
            "                                        { 0 }\n"
            "                                     };\n\n/* End of Generation */"
        )
        fd.close()

    pass

class PcbParse(LispParse):

    def __init__(self, filename):
        super(type(self), self).__init__()
        self.filename = filename
        fd = open(self.filename,r'r')
        code = fd.read()
        fd.close()
        code = self.preprocess(code)
        self.pcbnet = self.parse(code)[0]['kicad_pcb']

    def preprocess(self,code):
        import re
        code = re.sub(r'\(module[ ]*("[^"]*")([ ]*locked)', r'(module (name \1) (locked 1)', code)
        code = re.sub(r'\(module[ ]*([^(]*) \(', r'(module (name \1) (', code)
        code = re.sub(r'\(module[ ]*("[^"]*")', r'(module (name \1)', code)
        return code

    def analyse(self, netlist):
        global PP
        #PP.pprint(self.pcbnet)
        for elem in self.pcbnet['module']:
            if not 'descr' in elem or elem['descr'][0:7] != 'LED SMD': continue
            for txt in elem['fp_text']:
                if txt[0] == 'reference' and txt[1][0] == 'D':
                    ledId = int(txt[1][1:])-1
                    e_at = elem['at']
                    x = float(e_at[0])
                    y = float(e_at[1])
                    o = 0
                    pitch = 2.5
                    if len(e_at) > 2: o = int(e_at[2])
                    #print(str(ledId) + ' at ' +str(e_at))
                    # Perform a correction depending on the orientation.
                    if o ==   0: ( x, y ) = ( x + pitch/2, y )
                    if o ==  90: ( x, y ) = ( x, y - pitch/2 )
                    if o == 180: ( x, y ) = ( x - pitch/2, y )
                    if o == 270: ( x, y ) = ( x, y + pitch/2 )
                    netlist.leds[ledId]['x'] = x
                    netlist.leds[ledId]['y'] = y
    pass

PP = pprint.PrettyPrinter(indent=1, width=120)

def main():
    global PP
    parser = argparse.ArgumentParser()
    parser.add_argument('-n','--netfile', dest='netfile', help="Netlist file",     default="",    metavar=r'<file>')
    parser.add_argument('-p','--pcb',     dest='pcbfile', help="PCB file",         default="",    metavar=r'<file>')
    parser.add_argument('-d','--dump',    dest='pprint',  help="print netlist",    default=False, action='store_true')
    parser.add_argument('-t','--test',    dest='test'  ,  help="test lisp parser", default=False, action='store_true')
    args = parser.parse_args()

    if args.test:
        np = LispParse()
        PP.pprint(np.parse('(AND a b (OR c d)) (NOT foo) (AND (OR x y))'))
        # [{'AND': ['a', 'b', {'OR': ['c', 'd']}]}, {'NOT': ['foo']}, {'AND': [{'OR': ['x', 'y']}]}]

    nl = None
    if args.netfile != "":
        nl = NetParse(args.netfile)
        if args.pprint:
            #j = json.dumps(nl.netlist, indent=' ')
            PP.pprint(nl.description)
            PP.pprint(nl.nets)
        else:
            nl.analyse()
    if args.pcbfile != "":
        pcb = PcbParse(args.pcbfile)
        if args.pprint:
            #j = json.dumps(pcb.pcbnet, indent=' ')
            PP.pprint(pcb.pcbnet)
            pass
        else:
            if nl != None:
                pcb.analyse(nl)
                nl.generateTable()
    pass

def debug():
    r = lambda a: None
    r.netf="./PCB AFFICHEUR/PCB AFFICHEUR.net"
    r.pcbf="./PCB AFFICHEUR/PCB AFFICHEUR.kicad_pcb"
    r.nl=NetParse(r.netf)
    r.nl.analyse()
    r.pcb=PcbParse(r.pcbf)
    r.pcb.analyse()
    return r

def startProfile():
    import cProfile
    pr = cProfile.Profile()
    pr.enable()
    return pr

def stopProfile(pr):
    import io, pstats
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats()
    print(s.getvalue())

if __name__ == "__main__":
    #pr = startProfile()
    main()
    #stopProfile(pr)
