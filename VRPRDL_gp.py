import time
from gurobipy import *

import gurobipy as gp
import pandas as pd
from collections import defaultdict
import matplotlib.pyplot as plt
# 问题数据
data = pd.read_excel('C:/Users/Administrator/Desktop/instance_15.xlsx', engine='openpyxl')
num_vehicles = 5
num_locations = 49   # 配送点数量(不包括配送中心)
num_cluster = 15      # 配送点簇
locations = [(row['x'], row['y']) for _, row in data.iterrows()]
time_windows = [(row['start_time'], row['end_time']) for _, row in data.iterrows()]
cluster_demand = [int(row) for row in data['demand']]
# 根据需求对配送点进行分类
df = [(row['demand'], row['可接受的移动配送点']) for _, row in data.iterrows()]
cluster_dict = defaultdict(list)
for index, (key, value) in enumerate(df):
    cluster_dict[key].append(index)
# 将字典中的值转换为列表
cluster = list(cluster_dict.values())
del cluster[0]  #不包括仓库，15个客户的配送点
Max_capacity = 750
speed = 500  #米/分钟
#计算距离和旅行时间
def calculate_distance(loc1, loc2):
    return ((loc1[0] - loc2[0]) ** 2 + (loc1[1] - loc2[1]) ** 2) ** 0.5

distance = [[calculate_distance(locations[i], locations[j]) for j in range(num_locations + 2)] for i in range(num_locations + 2)]

#traveltimes = [[int(distance[i][j]*1000/speed) for j in range(num_locations + 2)] for i in range(num_locations + 2)]
traveltimes = [[distance[i][j]*1000/speed for j in range(num_locations + 2)] for i in range(num_locations + 2)]

#定义一个函数来绘制路线
def plot_routes(routes, locations, title="route"):
    plt.figure(figsize=(10, 10))
    plt.title(title)
    plt.xlabel('X')
    plt.ylabel('Y')

    # 绘制所有配送点
    for idx, coord in enumerate(locations):
        plt.scatter(coord[0], coord[1], color='blue', label='locations' if idx == 0 else "")
        plt.text(coord[0], coord[1], str(idx), fontsize=8)

    # 为每个车辆绘制路线
    colors = ['red', 'green', 'orange', 'purple', 'brown']  # 为不同车辆分配颜色
    for k, route in enumerate(routes):
        x = [locations[loc][0] for loc in route]
        y = [locations[loc][1] for loc in route]
        plt.plot(x, y, marker='o', linestyle='-', color=colors[k % len(colors)], label=f'vehicel{k + 1}')
        # 绘制箭头指示行驶方向（可选）
        for i in range(len(route) - 1):
            dx = x[i + 1] - x[i]
            dy = y[i + 1] - y[i]
            plt.arrow(x[i], y[i], dx, dy, head_width=0.1, head_length=0.1, fc=colors[k % len(colors)],
                      ec=colors[k % len(colors)])
    # 图例
    plt.legend()
    plt.grid(True)
    plt.show()

# 定义模型
model = gp.Model()
model.Params.TimeLimit = 7200
#model.params.MIPFocus = 1
model.Params.MIPGap = 0.00000000001
model.setParam("MIPFocus", 2)
model.setParam("Heuristics", 0.9)
x = [[[[] for _ in range(num_vehicles)] for _ in range(num_locations+2)] for _ in range(num_locations+2)]
s = [[[] for _ in range(num_vehicles)] for _ in range(num_locations+2)]    # 车辆k到达点j的时间(也是离开时间)
for i in range(num_locations+2):
    for k in range(num_vehicles):
        s[i][k] = model.addVar(lb=0, ub=max([tw[1] for tw in time_windows]), vtype=GRB.CONTINUOUS, name=f'S_{i}_{k}')
        for j in range(num_locations+2):
            x[i][j][k] = model.addVar(vtype=GRB.BINARY, name=f"x_{i}_{j}_{k}")
#加入目标函数
obj = gp.LinExpr()
for i in range(num_locations+1):
    for j in range(1, num_locations+2):
        for k in range(num_vehicles):
            obj += traveltimes[i][j]*x[i][j][k]
model.setObjective(obj, GRB.MINIMIZE)
model.update()
#加入约束

# 不能原地走
for i in range(num_locations+1):
    for j in range(1, num_locations+2):
        if i == j:
            for k in range(num_vehicles):
                model.addConstr(x[i][j][k] == 0)

# #每个客户仅被访问一次
for c in range(num_cluster):
    expr1 = 0
    for i in cluster[c]:
        for j in range(1, num_locations+2):
            for k in range(num_vehicles):
                expr1 += x[i][j][k]
    model.addConstr(expr1 == 1, name=f'constraint_{c+1}')

#每辆车从配送中心出发
for k in range(num_vehicles):
    expr2 = 0
    for j in range(1, num_locations+2):
        expr2 += x[0][j][k]
    model.addConstr(expr2 == 1, name=f'constraint_start_{k+1}')

# #网络流平衡约束
for k in range(num_vehicles):
    for j in range(1, num_locations+1):
        expr3_1 = gp.LinExpr()
        expr3_2 = gp.LinExpr()
        for i in range(num_locations+1):
            expr3_1 += x[i][j][k]
        for i in range(1, num_locations+2):
            expr3_2 += x[j][i][k]
        model.addConstr(expr3_1 == expr3_2, name=f'constraint_flow_{k+1}_{i}')
# # #车辆服务完返回车场
for k in range(num_vehicles):
    expr4 = 0
    for i in range(num_locations+1):
        expr4 += x[i][num_locations+1][k]
    model.addConstr(expr4 == 1, name=f"constraint_end_{k}")
# # # 子回路消除约束
M = 10000
for k in range(num_vehicles):
    for i in range(num_locations+2):
        for j in range(1, num_locations+2):
            expr5_1 = s[i][k] + traveltimes[i][j] - s[j][k]
            expr5_2 = M * (1 - x[i][j][k])
            model.addConstr(expr5_1 <= expr5_2, name=f"constraint_{k}_{i}_{j}")
# # #时间窗约束
for k in range(num_vehicles):
    for i in range(num_locations+1):
        expr6 = 0
        for j in range(1, num_locations+2):
            expr6 += x[i][j][k]
        model.addConstr(s[i][k] >= time_windows[i][0]*expr6, name=f"constraint_0_{k+1}_{i}")
        model.addConstr(s[i][k] <= time_windows[i][1]*expr6, name=f"constraint_1_{k+1}_{i}")

# #载重约束
for k in range(num_vehicles):
    for i in range(num_locations+2):
        expr7 = 0
        for j in range(num_locations+2):
            expr7 += cluster_demand[i] * x[i][j][k]
    model.addConstr(expr7 <= Max_capacity, name=f"constraint_cap_{k+1}")

model.update()
start_time = time.time()
model.optimize()

# 打印决策变量
# for i in model.getVars():
#     if i.x != 0:
#         print(i.VarName, i.x)
# print("目标函数值:", model.ObjVal)
# #
# model.computeIIS()
# model.write("model.ilp")
# print("IIS输出到文件model.ilp中")

# 输出路线
if model.Status == GRB.Status.OPTIMAL:
    print('找到最优解，总成本为:', model.objVal)
    print(f"求解时间:{time.time() - start_time} s")

    # 将所有车辆的路线整合
    all_routes = []
    for k in range(num_vehicles):
        print(f'车辆{k+1}的路线:')
        route = [0]
        current = 0
        while True:
            next_locations = -1
            for j in range(1, num_locations+1):
                if x[current][j][k].x > 0 and j not in route:  # 修改这里，考虑双向路径
                    next_locations = j
                    break

            if next_locations == -1:
                break
            route.append(next_locations)
            current = next_locations
        route.append(num_locations+1)  # 回到仓库
        print(route)
        all_routes.append(route)

    plot_routes(all_routes, locations)
else:
    print("未找到最优解")

