# STCL setpoint control from labscript

This folder contains the labscript-side code for controlling the RedPitaya STCL setpoints, as well as monitoring whether the lasers are still locked or not

## Setup
To add this to labscript, simply copy this (`RP_STCL`) folder to your user_devices labscript folder.

This code requires the lockclient_heros to be running on the network, you can find it in the top directory of this repo. You can run this script after setting up the zenoh as below, it will set the lasers up as in the config files, and then start the cavity scan and the monitor. You will need to enable the locks manually, files for this are also included in the github. 

 You will also need to configure a zenoh config json, and depending on your network, set up a zenohd server. I reccomend first trying the most basic setup, which has a zenoh config that looks like:
```
{
  mode: "peer",
}
```
and lets the clients in the network find each other automatically. However, some setups, like our CaF experiment, don't seem to play nicely with that, and so you would need to run a zenohd router [(find it here)](https://download.eclipse.org/zenoh/zenoh/latest/), and then the config should look something like:
```
{
  mode: "client",
  connect: {
    endpoints: ["tcp/192.168.0.2:7447"],
  },
}
```
where the 'endpoints' should be ways to reach the pc which runs the router. The second example can also be found in a json5 file in the examples folder.


## Usage
Once the lock is running, you can add the labscript device to the connection diagram like:
```
RP_STCL('lock','SCTL',parent_device=None, zenoh_config=r'S:\Codes\_current_experiment_ctrl_scripts\RedPitayaSTCL_labscript\examples\labscript\zenoh_config.json5',
        emon_ip='192.168.0.2', emon_port=6200, emon_tmin=0.03, error_margin=0.05, settle_timeout=10,error_on_unlock=True)
```
Here the arguments are:
```
Args:
        name (str): 
            The name of the device.
        heros_name (str): 
            The name of the remote heros object
        parent_device (Device,optional): 
            The parent device to which this device is connected. Defaults to None
        connection (string, optional): 
            The connection on the parent device, defaults to None
        zenoh_config (string, optional): 
            The location of the zenoh config json
        emon_ip (string or None, optional): 
            The IP address of the pc that will run the error monitor. If set to anything but none, the code will (re)start the error monitor with zmq publishing enabled for all interfaces at port emon_port
        emon_port (int, optional): 
            The port for the error monitor zmq stream. Defaults to 6200
        emon_tmin (float, optional): 
            minimum time between error monitor points
        error_margin (float or None, optional): 
            If not None, gives the error margin (in GHz) to wait for while laser is setteling. If none, disables wait. Defaults to None
        settle_timeout (float or None, optional): 
            If not None, gives the timeout for waiting for the laser to settle. 
        avg (int or None, optional): 
            If not None, sets number of averages for the rolling average, used for displaying the error, and also for checking at each shot if the laser is still locked
            If None, averaging is disabled. Defaults to 10
        error_on_unlock (bool, optional): 
            If set, the code will check at the beginning of each shot if the rolling average of the error has exceeded error_margin, and if it has, will error out. Defaults to True
```

We also need to add lasers to this, more on that below.

With the setup above, the code will (re)open the error monitor on the pc that's running the locking code, and start pulling error data from it. It displays it on the blacs front panel, with a rolling average of `avg` points, where the values will go red when the error value crosses the `error_margin` value. It will also start pulling it into the worker, again averaging `avg` points, and every time at the start of a shot, for each laser that has not had its setpoint changed, it will check if this value has not crossed the `error_margin`. If it has, it will throw an error and stop blacs. For each laser that has had a value set (more on that below), it starts getting instantaneous error values, and then waits at least 100ms and from there untill it receives a value below `error_margin`. If after `settle_timeout` seconds it has still not reached this point, it will error out.

The most basic version, where nothing is checked and we just set the setpoints, would be:
```
RP_STCL('lock','SCTL',parent_device=None, zenoh_config=r'zenoh_config.json5',  error_on_unlock=False)
```

## Adding lasers and setting setpoints
Lasers can be added to the code by setting them in the connection table. For instance, with the first setup above, we could add our vexlum like:
```
lock.add_laser('Vexlum','Lock1','Slave1')
```
This now makes it so that the code starts tracking the error of the vexlum, and allows us to set its setpoints in the experiment code like:
```
lock.Vexlum.update_lockpoint(lpoint)
```
where in this case `lpoint` is a global. The code supports smart programming, so setpoints are only sent if they're actually new (or at the first shot).



