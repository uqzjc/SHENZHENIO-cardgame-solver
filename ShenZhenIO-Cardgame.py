""" 深圳IO 卡牌游戏自动化脚本
本程序极大地参考了： https://github.com/Smankusors/shenzhen_solitaire_solver/blob/master/solver.js

使用 opencv 模块识别卡牌图像，并使用 pyautogui 模块模拟鼠标操作。
使用该脚本前请确保 深圳IO 游戏已经开启
"""
import cv2
import numpy as np
import pyautogui as pag
import time
from queue import PriorityQueue
from copy import deepcopy

# 可操作的常量
WAIT_TIME_FOR_START = 6 # 按下开始游戏后等待洗好牌的时间
WAIT_TIME_FOR_MOVE = 0.76 # 等待自动放置卡牌动画单位时间
WAIT_UNIT = 0.1 # 每次操作时间
WAIT_SLEEP_UNIT = 0.05 # 每次等待时间

# 游戏似乎不支持 click 方法，因此用按压/释放的方式模拟点击
def spClick(x, y):
    pag.moveTo(x, y,duration=WAIT_UNIT)
    pag.mouseDown()
    time.sleep(WAIT_UNIT)
    pag.mouseUp()
    time.sleep(WAIT_SLEEP_UNIT)

# 加载卡牌模板图像
imgMap = {}
for i in range(1,10):
    imgMap["r"+str(i)] = cv2.imread(f"assets/r{i}.png")
    imgMap["b"+str(i)] = cv2.imread(f"assets/b{i}.png")
    imgMap["g"+str(i)] = cv2.imread(f"assets/g{i}.png")
imgMap["B"] = cv2.imread(f"assets/B.png")
imgMap["R"] = cv2.imread(f"assets/R.png")
imgMap["G"] = cv2.imread(f"assets/G.png")
imgMap["F"] = cv2.imread(f"assets/F.png")
imgMap["empty"] = cv2.imread(f"assets/empty.png")

# 定义常量
ITMH, ITMW = 24, 24  # 卡牌大小
DISH, DISW = 31, 152 # 卡牌间距
BEGH, BEGW = 456,409 # 卡牌起始位置
CNTH, CNTW = 5, 8    # 卡牌行列数
NUM_TO_CHINESE = ['零','一','二','三','四','五','六','七','八','九'] # 数字转中文
CDLTH, CDLTW = 8,51  # 鼠标点击时偏移量
POPCOLORLOCATION = [(1216,234),(1370,234),(1521,234)]
cardList = []

# 定义状态
def canBeStacked(card1, card2):
    if len(card1) != 2 or len(card2) != 2: return False # 普通牌才能堆叠
    if card1[0] == card2[0]: return False # 相同花色不能堆叠
    return (int(card1[1]) + 1 == int(card2[1])) # 花色不同，数字相邻
class State:
    def __init__(self, prevState = None, action = None, customTrays = [[],[],[],[],[],[],[],[]],initColorHome = {'r':None, 'b':None, 'g':None}):
        if prevState is None:
            self.trays = customTrays
            self.slots = [None,None,None]
            self.cardHome = initColorHome
            self.cardHomeId = sum([1 if c is not None else 0 for c in initColorHome.values()])
            self.turn = 0
        else:
            self.trays = deepcopy(prevState.trays)
            self.slots = deepcopy(prevState.slots)
            self.cardHome = deepcopy(prevState.cardHome)
            self.cardHomeId = prevState.cardHomeId
            self.turn = prevState.turn + 1
        
        self.prevState = prevState
        # do action
        if action is not None:
            if "collapse" in action: # collapse
                target = action["collapse"]
                for tray in self.trays:
                    if len(tray) != 0 and tray[-1] == target:
                        tray.pop()
                for i,slot in enumerate(self.slots):
                    if slot == target: self.slots[i] = None
                for i in range(len(self.slots)):
                    if self.slots[i] is None:
                        self.slots[i] = 'X'
                        break
            elif "pop" in action: # pop
                self.trays[action["pop"]].pop()
            else: # move
                cardsToBeRemoved = []
                if "tray" in action["from"]:
                    for i in range(action["from"]["count"]):
                        cardsToBeRemoved.append(self.trays[action["from"]["tray"]].pop())
                else:
                    cardsToBeRemoved.append(self.slots[action["from"]["slot"]])
                    self.slots[action["from"]["slot"]] = None
                cardsToBeRemoved.reverse()
                if "tray" in action["to"]:
                    self.trays[action["to"]["tray"]].extend(cardsToBeRemoved)
                else:
                    self.slots[action["to"]["slot"]] = cardsToBeRemoved[0]
        # auto remove cards
        self.autoRemoveTimes = 0
        self.autoRemoveCards()
        self.action = action
        self.remainingCards = sum([len(t) for t in self.trays]) + sum([1 if (s is not None) and s != 'X' else 0 for s in self.slots])
        self.priority = self.calcPriority()

    def __lt__(self, other): # 用于优先队列
        return self.priority < other.priority

    def autoRemoveCards(self): # 自动移除卡牌
        callAgainFlag = True
        counts = 0
        while callAgainFlag:
            counts += 1
            if counts > 1000:
                print("卡牌自动移除失败")
                print(self.trays)
                print(self.slots)
                outputHowToArriveAtState(self)
                raise Exception("卡牌自动移除失败")
            callAgainFlag = False
            self.lowestPersuit = {'r':10, 'b':10, 'g':10}
            for i,tray in enumerate(self.trays):
                if len(tray) == 0: continue
                lastCard = tray[-1]
                if lastCard == 'F':
                    self.trays[i].pop()
                    callAgainFlag = 1
                elif (len(lastCard)==2 and lastCard[1] == '1'):
                    self.cardHome[lastCard[0]] = self.cardHomeId
                    self.cardHomeId += 1
                    self.trays[i].pop()
                    callAgainFlag = 1
                for card in tray:
                    if len(card) == 2 and int(card[1])<self.lowestPersuit[card[0]]:
                        self.lowestPersuit[card[0]] = int(card[1])
            for slotCard in self.slots:
                if slotCard is not None and len(slotCard) == 2 and int(slotCard[1])<self.lowestPersuit[slotCard[0]]:
                    self.lowestPersuit[slotCard[0]] = int(slotCard[1])
            for i,tray in enumerate(self.trays):
                if len(tray) == 0: continue
                lastCard = tray[-1]
                if len(lastCard) != 2: continue
                value = int(lastCard[1])
                if value > 2:
                    if value <= self.lowestPersuit['r'] and value <= self.lowestPersuit['b'] and value <= self.lowestPersuit['g']:
                        self.trays[i].pop()
                        callAgainFlag = 2
                elif value == 2 and value == self.lowestPersuit[lastCard[0]]:
                    self.trays[i].pop()
                    callAgainFlag = 3
            for i,slotCard in enumerate(self.slots):
                if slotCard is None or len(slotCard) != 2: continue
                value = int(slotCard[1])
                if value > 2:
                    if value <= self.lowestPersuit['r'] and value <= self.lowestPersuit['b'] and value <= self.lowestPersuit['g']:
                        self.slots[i] = None
                        callAgainFlag = 4
                elif value == 2 and value == self.lowestPersuit[slotCard[0]]:
                    self.slots[i] = None
                    callAgainFlag = 5
        self.autoRemoveTimes = counts-1

    def getValidTrayActions(self):
        trays = self.trays
        result = []
        exposedDragons = {'R': 0, 'B': 0, 'G': 0}
        for (i,tray) in enumerate(trays):
            if len(tray) == 0: continue
            lastCard = tray[-1]
            if len(lastCard) == 1: # 特殊牌
                exposedDragons[lastCard] += 1
            elif self.lowestPersuit[lastCard[0]] == int(lastCard[1]):
                result.append({"pop": i})
            for (cid,card) in enumerate(reversed(tray)):
                for (j,tray2) in enumerate(trays):
                    if i == j: continue
                    if len(tray2) > 0:
                        target = tray2[-1]
                        if canBeStacked(card, target):
                            result.append({"from": {"tray": i, "count": cid+1}, "to": {"tray": j}})
                    elif cid != len(tray)-1: # 非移动整堆牌
                        result.append({"from": {"tray": i, "count": cid+1}, "to": {"tray": j}})
                if cid != len(tray)-1 and not canBeStacked(card,tray[len(tray)-cid-2]):
                    break
        slotAvailableForDragonFlag = False
        slotAvailableForSpecificDragonFlag = {'R': False, 'B': False, 'G': False}
        for i,slotCard in enumerate(self.slots):
            if slotCard is None:
                slotAvailableForDragonFlag = True
                continue
            if slotCard == 'X': continue
            for j,tray in enumerate(self.trays):
                if (len(tray)>0 and canBeStacked(slotCard, tray[-1])) or len(tray)==0:
                    result.append({"from": {"slot": i}, "to": {"tray": j}})
            if len(slotCard) == 1:
                slotAvailableForSpecificDragonFlag[slotCard[0]] = True
                exposedDragons[slotCard[0]] += 1
        for dragon in ['R', 'B', 'G']:
            if exposedDragons[dragon] == 4 and (slotAvailableForDragonFlag or slotAvailableForSpecificDragonFlag[dragon]):
                result.append({"collapse": dragon})
        return result
    def getValidSlotActions(self):
        result = []
        for (i,tray) in enumerate(self.trays):
            if len(tray) == 0: continue
            for (j,slotCard) in enumerate(self.slots):
                if slotCard is None:
                    result.append({"from": {"tray": i, "count": 1}, "to": {"slot": j}})
        return result
    
    def calcPriority(self): # 计算优先级
        stackedCards = 0
        for tray in self.trays:
            if len(tray) == 0: continue
            localStackedCards = 0
            for i in range(len(tray)-1,0,-1):
                if canBeStacked(tray[i], tray[i-1]):
                    localStackedCards += 1
            if len(tray)>1 and localStackedCards == len(tray)-1:
                if int(tray[0][1]) == 9:
                    stackedCards += localStackedCards * 1.2
                else: stackedCards += localStackedCards * 1.1
            else: stackedCards += localStackedCards
        if self.remainingCards == 0 : return -999
        if self.remainingCards < 10: return -100 + self.remainingCards + self.turn*0.1
        return self.remainingCards + self.turn*0.1 - stackedCards*0.9

    def __hash__(self):
        result = ""
        for tray in self.trays:
            result += ",".join(tray) + ";"
        result += "|"
        for slot in self.slots:
            if slot is None: result += "*;"
            else: result += slot + ";"
        return hash(result)

def verifyState(q:PriorityQueue[State], visitedStates:set, currentState:State, actions:list[dict]):
    validActions = 0
    for action in actions:
        newState = State(currentState, action)
        stateHash = hash(newState)
        if stateHash not in visitedStates:
            validActions += 1
            q.put(newState)
            visitedStates.add(stateHash)
    return validActions

def solve(initialTrays:list[list[str]], colorHome:dict):
    if len(initialTrays) != CNTW:
        print("当前局面输入错误")
        return None
    zeroTag = True
    for tray in initialTrays:
        if len(tray) != 0:
            zeroTag = False
            break
    if zeroTag:
        print("当前局面输入错误，请求人工介入")
    initialState = State(customTrays=initialTrays, initColorHome=colorHome)
    q = PriorityQueue(); q.put(initialState)
    iteration = 0
    visitedStates = {hash(initialState)}
    while iteration < 1e4 and (not q.empty()):
        curState = q.get()
        if curState.remainingCards == 0:
            print("经过", iteration, "次迭代，已找到必胜方案")
            return curState
        actions = curState.getValidTrayActions()
        if verifyState(q,visitedStates,curState,actions) == 0:
            actions = curState.getValidSlotActions()
            verifyState(q,visitedStates,curState,actions)
        if iteration % 1e3 == 0:
            print("寻找方案中，已进行", iteration,"次迭代，已探索",len(visitedStates),"个状态，队列中还有",q.qsize(),"个状态","当前堆顶优先级",curState.priority)
        iteration += 1
    print("没找到必胜方案，重开吧")
    return None

def outputCardList(cardList):
    for i in range(CNTW):
        print("第"+NUM_TO_CHINESE[i+1]+"槽：",end="")
        for card in cardList[i]:
            if card == "F": print("花牌 ", end="")
            elif card == "B": print("白板 ", end="")
            elif card == "R": print("红中 ", end="")
            elif card == "G": print("发财 ", end="")
            else:
                if card[0] == "r": print(NUM_TO_CHINESE[int(card[1])]+"筒 ", end="")
                elif card[0] == "b": print(NUM_TO_CHINESE[int(card[1])]+"万 ", end="")
                else: print(NUM_TO_CHINESE[int(card[1])]+"条 ", end="")
        print()

if __name__ == '__main__':
    # 寻找窗口
    gameWindow = pag.getWindowsWithTitle("SHENZHEN I/O")
    if len(gameWindow) == 0 or gameWindow[0] is None:
        print("Game window not found")
        exit(1)
    gameWindow = gameWindow[0]
    print("Game window found")
    # 调整窗口位置 - 归一化图像
    gameWindow.activate()
    gameWindow.maximize()
    gameWindow.move(0, 0)
    gameWindow.resizeTo(1920, 1200)
    time.sleep(WAIT_SLEEP_UNIT)
    spClick(21,500)
    time.sleep(WAIT_SLEEP_UNIT)
    screen = pag.screenshot(region=(0, 0, 1920, 1080))
    img = cv2.cvtColor(np.array(screen), cv2.COLOR_RGB2BGR)
    target = cv2.imread(r"assets/where-to-click.png")
    res = cv2.matchTemplate(img, target, cv2.TM_CCOEFF_NORMED)
    _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
    if maxVal > 0.8:
        pag.moveTo(maxLoc[0], maxLoc[1], duration=WAIT_UNIT)
        print("Found where to click on screen")
    else:
        pag.moveTo(920,1016, duration=WAIT_UNIT)
    pag.mouseDown()
    time.sleep(WAIT_UNIT)
    pag.mouseUp()
    time.sleep(WAIT_SLEEP_UNIT)
    # 截图并识别
    while True:
        cardList = []
        time.sleep(0.5)
        spClick(1511,993)
        time.sleep(WAIT_TIME_FOR_START)
        pagScreen = pag.screenshot(region=(0, 0, 1920, 1080))
        img = cv2.cvtColor(np.array(pagScreen), cv2.COLOR_RGB2BGR)
        colorHome = {'r':None, 'b':None, 'g':None}
        for i in range(3):
            colorHome1 = img[208,1179+i*DISW]
            if np.array_equal(colorHome1,(0,0,0)):
                colorHome['b'] = i
            elif np.array_equal(colorHome1,(75,110,18)):
                colorHome['g'] = i
            elif np.array_equal(colorHome1,(20,44,174)):
                colorHome['r'] = i
        print("初始右上角区域颜色：")
        print("筒子", "在 "+NUM_TO_CHINESE[colorHome['r']] if colorHome['r'] is not None else "不在",sep="")
        print("万子", "在 "+NUM_TO_CHINESE[colorHome['b']] if colorHome['b'] is not None else "不在",sep="")
        print("条子", "在 "+NUM_TO_CHINESE[colorHome['g']] if colorHome['g'] is not None else "不在",sep="")
        for nw in range(CNTW):
            cardSubGroup = []
            for nh in range(CNTH):
                x, y = BEGW + nw*DISW, BEGH + nh*DISH
                curDict = {}
                for (cardName, cardImg) in imgMap.items():
                    res = cv2.matchTemplate(img[y:y+ITMH, x:x+ITMW], cardImg, cv2.TM_CCOEFF_NORMED)
                    _, maxVal, _, maxLoc = cv2.minMaxLoc(res)
                    curDict[cardName] = maxVal
                maxCard = max(curDict, key=curDict.get)
                if maxCard != "empty" and curDict[maxCard] > 0.8:
                    cardSubGroup.append(maxCard)
            cardList.append(cardSubGroup)
        # 输出卡牌列表
        outputCardList(cardList)
        # 寻找必胜方案
        solveState = solve(cardList, colorHome)
        if solveState is not None:
            stateList = []
            curState = solveState
            while curState.turn != 0:
                stateList.append(curState)
                curState = curState.prevState
            stateList.reverse()
            preState = curState
            for state in stateList:
                print("第",state.turn,"回合操作：",end="")
                method = state.action
                if "collapse" in method:
                    if method["collapse"] == 'R':
                        print("拆掉红中")
                        spClick(888,217) 
                    elif method["collapse"] == 'B':
                        print("拆掉白板")
                        spClick(888,385)
                    elif method["collapse"] == 'G':
                        print("拆掉发财")
                        spClick(888,303)
                elif "pop" in method:
                    print("从第",method["pop"]+1,"堆中弹出一张牌")
                    xid = method["pop"]; yid = len(preState.trays[xid])-1
                    cardColor = preState.trays[xid][-1][0]
                    colorId = state.cardHome[cardColor]
                    pag.moveTo(BEGW+xid*DISW+CDLTW,BEGH+yid*DISH+CDLTH)
                    time.sleep(WAIT_SLEEP_UNIT)
                    pag.mouseDown()
                    pag.moveTo(POPCOLORLOCATION[colorId][0],POPCOLORLOCATION[colorId][1], duration=WAIT_UNIT)
                    pag.mouseUp()
                    time.sleep(WAIT_SLEEP_UNIT)
                else:
                    if "tray" in method["from"] and "tray" in method["to"]:
                        print("从",method["from"]["tray"]+1,"堆移",method["from"]["count"],"到",method["to"]["tray"]+1,"堆")
                        xfid = method["from"]["tray"]; yfid = len(preState.trays[xfid])-method["from"]["count"]
                        xtid = method["to"]["tray"]; ytid = len(preState.trays[xtid])
                        pag.moveTo(BEGW+xfid*DISW+CDLTW,BEGH+yfid*DISH+CDLTH, duration=WAIT_UNIT)
                        time.sleep(WAIT_SLEEP_UNIT)
                        pag.mouseDown()
                        pag.moveTo(BEGW+xtid*DISW+CDLTW,BEGH+ytid*DISH+CDLTH, duration=WAIT_UNIT)
                        pag.mouseUp()
                        time.sleep(WAIT_SLEEP_UNIT)
                    elif "slot" in method["from"] and "tray" in method["to"]:
                        print("从",method["from"]["slot"]+1,"槽到",method["to"]["tray"]+1,"堆")
                        xfid = method["from"]["slot"]
                        xtid = method["to"]["tray"]; ytid = len(preState.trays[xtid])
                        pag.moveTo(457+xfid*DISW,200, duration=WAIT_UNIT)
                        time.sleep(WAIT_SLEEP_UNIT)
                        pag.mouseDown()
                        pag.moveTo(BEGW+xtid*DISW+CDLTW,BEGH+ytid*DISH+CDLTH, duration=WAIT_UNIT)
                        pag.mouseUp()
                        time.sleep(WAIT_SLEEP_UNIT)
                    elif "tray" in method["from"] and "slot" in method["to"]:
                        print("从",method["from"]["tray"]+1,"堆移到",method["to"]["slot"]+1,"槽")
                        xfid = method["from"]["tray"]; yfid = len(preState.trays[xfid])-1
                        xtid = method["to"]["slot"]
                        pag.moveTo(BEGW+xfid*DISW+CDLTW,BEGH+yfid*DISH+CDLTH, duration=WAIT_UNIT)
                        time.sleep(WAIT_SLEEP_UNIT)
                        pag.mouseDown()
                        pag.moveTo(457+xtid*DISW,200, duration=WAIT_UNIT)
                        pag.mouseUp()
                        time.sleep(WAIT_SLEEP_UNIT)
                preState = state
                time.sleep(WAIT_TIME_FOR_MOVE*state.autoRemoveTimes)
        time.sleep(WAIT_UNIT)
        
    
def outputHowToArriveAtState(state:State):
    if state is not None:
        methodList = []
        curState = state
        while curState.turn != 0:
            methodList.append(curState)
            curState = curState.prevState
        methodList.reverse()
        for state in methodList:
            if not hasattr(state, "action"):
                print("最终状态")
                continue
            method = state.action
            print("第",state.turn,"回合")
            if "collapse" in method:
                print("将",method["collapse"],"拆掉")
            elif "pop" in method:
                print("从第",method["pop"]+1,"张牌堆中弹出一张牌")
            else:
                if "tray" in method["from"] and "tray" in method["to"]:
                    print("将第",method["from"]["tray"]+1,"张牌堆的第",method["from"]["count"],"张牌移到",method["to"]["tray"]+1,"牌堆")
                elif "slot" in method["from"] and "tray" in method["to"]:
                    print("将第",method["from"]["slot"]+1,"个槽位的牌移到",method["to"]["tray"]+1,"张牌堆")
                elif "tray" in method["from"] and "slot" in method["to"]:
                    print("将第",method["from"]["tray"]+1,"张牌堆的第",method["from"]["count"],"张牌移到第",method["to"]["slot"]+1,"个槽位")
                else:
                    print("未知操作：",method)

            print("得到：")
            outputCardList(state.trays)
            print("托盘：")
            for slotCard in state.slots:
                if slotCard is None: print("空 ", end="")
                elif slotCard == 'X': print("X ", end="")
                elif slotCard == 'F': print("花牌 ", end="")
                elif slotCard == 'B': print("白板 ", end="")
                elif slotCard == 'R': print("红中 ", end="")
                elif slotCard == 'G': print("发财 ", end="")
                else:
                    if slotCard[0] == "r": print(NUM_TO_CHINESE[int(slotCard[1])]+"筒 ", end="")
                    elif slotCard[0] == "b": print(NUM_TO_CHINESE[int(slotCard[1])]+"万 ", end="")
                    else: print(NUM_TO_CHINESE[int(slotCard[1])]+"条 ", end="")
            print()