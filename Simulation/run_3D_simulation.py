# -*- coding: utf-8 -*-
"""
author: John Bass
email: john.bobzwik@gmail.com
license: MIT
Please feel free to use and modify this, but keep the above information. Thanks!
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import cProfile

from trajectory import Trajectory
from potentialField import PotField
from ctrl import Control
from quadFiles.quad import Quadcopter
from utils.windModel import Wind
import utils
import config

deg2rad = np.pi/180.0

sim_hz = []

def makeWaypoints(init_pose, wp, yaw, total_time=5):
    
    wp = np.vstack((init_pose[:3], wp)).astype(float)
    yaw = np.hstack((init_pose[-1], yaw)).astype(float)*deg2rad

    # For pos_waypoint_arrived_wait, this time will be the 
    # amount of time waiting
    t = np.linspace(0, total_time, wp.shape[0])
    dist = np.sum([((i-e)**2)**0.5 for i,e in zip(wp[:-1],wp[1:])])
    v_average = dist/total_time

    return t, wp, yaw, v_average


def quad_sim(t, Ts, quad, ctrl, wind, traj, potfld):

    # Dynamics (using last timestep's commands)
    # ---------------------------    
    quad.update(t, Ts, ctrl.w_cmd, wind)
    t += Ts

    # Trajectory for Desired States 
    # ---------------------------
    traj.desiredState(t, Ts, quad)        

    # Generate Commands (for next iteration)
    # ---------------------------
    ctrl.controller(traj, quad, potfld, Ts)

    return t
    

def main():
    # Simulation Setup
    # --------------------------- 
    Ti = 0 # init time

    # Testing sample periods
    # Ts = 0.0025 # 985Hz
    Ts = 0.005 # 880Hz
    # Ts = 0.0075 # 632Hz
    # Ts = 0.01 # 595Hz
    # Ts = 0.02 # 389Hz 
    # the ode solver struggles to reach the min error 
    # when Ts is too big, therefore it takes more iterations
    Tf = 100 # max sim time
    
    # save the animation
    ifsave = 0

    # Choose trajectory settings
    # --------------------------- 
    ctrlOptions = ["xyz_pos", "xy_vel_z_pos", "xyz_vel"]
    trajSelect = np.zeros(3)

    # Select Control Type             (0: xyz_pos,                  1: xy_vel_z_pos,            2: xyz_vel)
    ctrlType = ctrlOptions[0]

    # Select Position Trajectory Type (0: hover,                    1: pos_waypoint_timed,      2: pos_waypoint_interp,    
    #                                  3: minimum velocity          4: minimum accel,           5: minimum jerk,           6: minimum snap
    #                                  7: minimum accel_stop        8: minimum jerk_stop        9: minimum snap_stop
    #                                 10: minimum jerk_full_stop   11: minimum snap_full_stop
    #                                 12: pos_waypoint_arrived     13: pos_waypoint_arrived_wait
    trajSelect[0] = 12         

    # Select Yaw Trajectory Type      (0: none                      1: yaw_waypoint_timed,      2: yaw_waypoint_interp     3: follow          4: zero)
    trajSelect[1] = 3           

    # Select if waypoint time is used, or if average speed is used to calculate waypoint time   (0: waypoint time,   1: average speed)
    trajSelect[2] = 1           

    print("Control type: {}".format(ctrlType))

    # Initialize Quadcopter, Controller, Wind, Result Matrixes
    # ---------------------------
    init_pose = [10,10,-10,0,0,0] # in NED
    init_twist = [0,0,-10,0,0,0] # in NED
    init_states = np.hstack((init_pose,init_twist))

    wp = np.array([[2, 2, -1],
                   [-2, 3, -3],
                   [-2, -1, -3],
                   [3, -2, -1],
                   [-3, 2, -1]])

    yaw = np.array([10,
                    20, 
                   -90, 
                   120, 
                   45])
    desired_traj = makeWaypoints(init_pose, wp, yaw, total_time=20)

    potfld = PotField(pfType=1,importedData=np.zeros((0,3),dtype=float))

    quad = Quadcopter(Ti, init_states)
    traj = Trajectory(quad, ctrlType, trajSelect, desired_traj, dist_consider_arrived=1)
    ctrl = Control(quad, traj.yawType)
    wind = Wind('None', 2.0, 90, -15)
    potfld.isWithinRange(quad)
    potfld.isWithinField(quad)        
    potfld.rep_force(quad, traj)


    # Trajectory for First Desired States
    # ---------------------------
    traj.desiredState(0, Ts, quad)        

    # Generate First Commands
    # ---------------------------
    ctrl.controller(traj, quad, potfld, Ts)
    
    # Initialize Result Matrixes
    # ---------------------------
    numTimeStep = int(Tf/Ts+1)

    t_all          = []
    s_all          = []
    pos_all        = []
    vel_all        = []
    quat_all       = []
    omega_all      = []
    euler_all      = []
    sDes_traj_all  = []
    sDes_calc_all  = []
    w_cmd_all      = []
    wMotor_all     = []
    thr_all        = []
    tor_all        = []
    potfld_all     = []
    fieldPointcloud = []

    t_all.append(Ti)
    s_all.append(quad.state)
    pos_all.append(quad.pos)
    vel_all.append(quad.vel)
    quat_all.append(quad.quat)
    omega_all.append(quad.omega)
    euler_all.append(quad.euler)
    sDes_traj_all.append(traj.sDes)
    sDes_calc_all.append(ctrl.sDesCalc)
    w_cmd_all.append(ctrl.w_cmd)
    wMotor_all.append(quad.wMotor)
    thr_all.append(quad.thr)
    tor_all.append(quad.tor)
    potfld_all.append(potfld.F_rep)
    fieldPointcloud.append(potfld.fieldPointcloud)

    wall = np.random.rand(500,3)
    wall[:,0] = wall[:,0]*5-2.5
    wall[:,1] = 0
    wall[:,2] = -wall[:,2]*5

    # Run Simulation
    # ---------------------------
    t = Ti
    i = 1
    start_time = time.time()
    while (round(t,3) < Tf) and (i < numTimeStep) and not (all(traj.desPos == traj.wps[-1,:]) and sum(abs(traj.wps[-1,:]-quad.pos)) <= traj.dist_consider_arrived):
        t_ini = time.monotonic()
        potfld = PotField(pfType=1, importedData=wall, rangeRadius=5, fieldRadius=3, kF=1)
        potfld.isWithinRange(quad)
        potfld.isWithinField(quad)        
        potfld.rep_force(quad, traj)
        t = quad_sim(t, Ts, quad, ctrl, wind, traj, potfld)
        
        # print("{:.3f}".format(t))
        t_all.append(t)
        s_all.append(quad.state)
        pos_all.append(quad.pos)
        vel_all.append(quad.vel)
        quat_all.append(quad.quat)
        omega_all.append(quad.omega)
        euler_all.append(quad.euler)
        sDes_traj_all.append(traj.sDes)
        sDes_calc_all.append(ctrl.sDesCalc)
        w_cmd_all.append(ctrl.w_cmd)
        wMotor_all.append(quad.wMotor)
        thr_all.append(quad.thr)
        tor_all.append(quad.tor)
        potfld_all.append(potfld.F_rep)
        fieldPointcloud.append(potfld.fieldPointcloud)
        
        i += 1
        sim_hz.append(1/(time.monotonic()-t_ini))
    
    total_time = time.time() - start_time
    print(f"Simulated {t:.2f}s in {total_time:.2f}s or {t/total_time:.2}X - sim_hz [max,min,avg]: {max(sim_hz):.4f},{min(sim_hz):.4f},{sum(sim_hz)/len(sim_hz):.4f}")

    # View Results
    # ---------------------------

    t_all = np.asanyarray(t_all)
    s_all = np.asanyarray(s_all)
    pos_all = np.asanyarray(pos_all)
    vel_all = np.asanyarray(vel_all)
    quat_all = np.asanyarray(quat_all)
    omega_all = np.asanyarray(omega_all)
    euler_all = np.asanyarray(euler_all)
    sDes_traj_all = np.asanyarray(sDes_traj_all)
    sDes_calc_all = np.asanyarray(sDes_calc_all)
    w_cmd_all = np.asanyarray(w_cmd_all)
    wMotor_all = np.asanyarray(wMotor_all)
    thr_all = np.asanyarray(thr_all)
    tor_all = np.asanyarray(tor_all)
    potfld_all = np.asanyarray(potfld_all)
    fieldPointcloud = np.array(fieldPointcloud, dtype=object)

    # utils.fullprint(sDes_traj_all[:,3:6])
    # utils.makeFigures(quad.params, t_all, pos_all, vel_all, quat_all, omega_all, euler_all, w_cmd_all, wMotor_all, thr_all, tor_all, sDes_traj_all, sDes_calc_all)
    ani = utils.sameAxisAnimation(t_all, traj.wps, pos_all, quat_all, sDes_traj_all, Ts, quad.params, traj.xyzType, traj.yawType, ifsave, wall, potfld_all, fieldPointcloud)
    plt.show()

if __name__ == "__main__":
    if (config.orient == "NED" or config.orient == "ENU"):
        main()
        # cProfile.run('main()')
    else:
        raise Exception("{} is not a valid orientation. Verify config.py file.".format(config.orient))