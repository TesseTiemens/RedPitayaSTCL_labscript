from blacs.device_base_class import DeviceTab
from qtutils.qt.QtWidgets import *
from qtutils.qt.QtCore import *
from qtutils.qt.QtGui import *
import zmq
import threading
import time
import numpy as np

class lock_zmqThread_QT(threading.Thread):
    """
    Special threading class that can be nicely stopped and handles all of the zmq backbone for us.
    Updates a 
    """
    colorNormal = "#000000"
    colorError = "#FF0000"
    def __init__(self,stream,parent,avg=20):
        self.stream=stream
        self.address = stream['addr']
        self.port = stream['port']
        self.dt = stream['dt']
        self.topic = f"{stream['lock']} : {stream['slave']}"
        self.parent=parent
        self.avg = stream['avg']
        if self.avg:
            self.avgarr = np.zeros(self.avg)

        #register the please stop as event that can be called at any time
        self._please_stop = threading.Event()

        threading.Thread.__init__(self,daemon=True)

    def run(self):
        #we set up a zmq subscriber
        with zmq.Context().socket(zmq.SUB) as socket: #do a with so it natually closes the socket at the end
            socket.setsockopt(zmq.SUBSCRIBE, self.topic.encode('UTF-8'))
            socket.setsockopt(zmq.RCVHWM,1)
            socket.RCVTIMEO = int(np.floor(2*self.dt*1000)) #dt is in seconds, rcvtimeo is in ms
            socket.connect(f"tcp://{self.address}:{self.port}")

            #loop untill we need to stop
            while not self._please_stop.is_set():
                try:
                    msg = socket.recv().decode('utf-8')
                    #print(msg)
                    val_list = msg.split(';') #we split after the topic, assuming it's [topic]: [value]
                    
                    try: #try converting the thing to float so we can do formatting
                        val_new = float(val_list[-1])

                        if self.avg is not None: #run the rolling average if this is set
                            #rint(val_new)
                            self.avgarr[0] = val_new
                            self.avgarr = np.roll(self.avgarr,1) #step over one to keep a rolling average
                            val = np.average(self.avgarr)
                            #print(self.avgarr)
                        else:
                            val = val_new

                        #check against the max error before we mult
                        if self.stream['emax'] is not None and np.abs(val)>self.stream['emax']:
                            tcolor = self.colorError
                        else:
                            tcolor = self.colorNormal
                        val *= self.stream['mult'] #in case we need to do any conversions
                        

                        if self.stream['precision'] is not None:
                            if self.stream['sci']:
                                self.parent.update_value(f"<font color={tcolor}>{val:.{self.stream['precision']}e} {self.stream['unit']}</font>")
                            else:
                                self.parent.update_value(f"<font color={tcolor}>{val:.{self.stream['precision']}f} {self.stream['unit']}</font>")
                        else:
                            if self.stream['sci']:
                                self.parent.update_value(f"<font color={tcolor}>{val:e} {self.stream['unit']}</font>")
                            else:
                                self.parent.update_value(f"<font color={tcolor}>{val:f} {self.stream['unit']}</font>")
                    except:
                        self.parent.update_value(f"{val_list[-1]} {self.stream['unit']}")
                except Exception as e: #mainly here to catch timeouts but I'm not sure what exception that throws
                    if isinstance(e,zmq.error.Again):
                        pass #ignore resource temp unavailable errors to avoid flooding the terminal 
                    else:
                        print('Something went wrong!')
                        print(e)
                    
                #wait before trying to receive again. Since we ask the user to set dt to the exact send dt, we should here wait less than that to allow for the processing above
                #the timeout will take care of any other waiting.
                time.sleep(self.dt/2)
                
    def stop(self):
        self._please_stop.set()

class lock_LabelDisplay(QObject):
    """
    A reusable display widget with two stacked QLabels inside a bordered frame.
    The top label is smaller (e.g. a channel name or status),
    the bottom label is larger (e.g. a current value or message).

    Modelled after the DDS output class pattern: instantiate it, place
    `self.widget` into your layout, and call `set_top()`/`set_bottom()`
    to update the displayed text.

    Tweaked to start a zmq listener that listens to the same as the logging process
    in the worker, and continuously updates teh buttom value.
    """

    BORDER_COLOUR = '#4a90d9'
    BG_COLOUR = '#f5f8fc'

    _val_changed = Signal(str)

    def __init__(self, laser):
        """
        Args:
            name: a label shown in the top field by default (e.g. channel name)
            top_text: initial text for the top (small) label
            bottom_text: initial text for the bottom (large) label
        """
        super().__init__()
        self.name = laser['name']

        # --- Outer bordered frame (this is the thing you add to a layout) ---
        self._frame = QFrame()
        self._frame.setFrameShape(QFrame.StyledPanel)
        self._frame.setFrameShadow(QFrame.Sunken)
        self._frame.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {self.BORDER_COLOUR};
                border-radius: 6px;
                background-color: {self.BG_COLOUR};
            }}
        """)

        frame_layout = QVBoxLayout()
        frame_layout.setSpacing(8)
        frame_layout.setContentsMargins(10, 8, 10, 8)
        self._frame.setLayout(frame_layout)

        # --- Top label (small) ---
        self._label_top = QLabel(laser['name'])
        self._label_top.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._label_top.setWordWrap(True)
        self._label_top.setStyleSheet('border: none; color: #555;')
        font_top = QFont()
        font_top.setPointSize(9)
        self._label_top.setFont(font_top)

        # --- Bottom label (large) ---
        self._label_bottom = QLabel('—')
        self._label_bottom.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._label_bottom.setWordWrap(True)
        self._label_bottom.setStyleSheet('border: none; color: #111;')
        self._label_bottom.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._label_bottom.setMinimumHeight(60)
        font_bottom = QFont()
        font_bottom.setPointSize(14)
        font_bottom.setBold(True)
        self._label_bottom.setFont(font_bottom)

        #add labels to frame
        frame_layout.addWidget(self._label_top)
        frame_layout.addWidget(self._label_bottom)

        #connect the update signal to the right function
        self._val_changed.connect(self._label_bottom.setText,)# Qt.QueuedConnection)

        #start the listener thread
        self.zthread = lock_zmqThread_QT(laser,self)
        self.zthread.start()

    @property
    def widget(self):
        """The QFrame to add to your layout."""
        return self._frame
    
    def update_value(self,text):
        self._val_changed.emit(text)
        #self._label_bottom.setText(text)

class STCLTab(DeviceTab):
    def initialise_GUI(self):
        self.outputs = []
        self.zthreads = []
        self.streams = []
        properties = self.connection_table.find_by_name(self.device_name).properties
        lasers = properties['lasers']
        addr = properties['emon_ip']
        port = properties['emon_port']
        dt = properties['emon_tmin']
        emax = properties['error_margin']
        avg = properties['avg']
        layout = self.get_tab_layout()

        #create a widget and listener thread for each stream
        if addr is not None:
            for laser in lasers:
                laserstream = laser.copy()
                laserstream['addr'] = addr
                laserstream['port'] = port
                laserstream['dt']  = dt
                laserstream['emax'] = emax
                laserstream['unit'] = 'MHz'
                laserstream['mult'] = 1000
                laserstream['precision'] = 3
                laserstream['sci'] = False
                laserstream['avg'] = avg
                self.streams.append(laserstream)
                self.outputs.append(lock_LabelDisplay(laserstream))
                self.zthreads.append(self.outputs[-1].zthread)
                layout.addWidget(self.outputs[-1].widget)
        layout.addStretch()
        self.auto_place_widgets()
    
        self.supports_smart_programming(True)
    
    
    # def initialise_workers(self):
        #I'm not sure what the order of starting stuff is but I want the code above to run before starting the worker
        worker_initialisation_kwargs = self.connection_table.find_by_name(self.device_name).properties
        worker_initialisation_kwargs['streams'] = self.streams
        print(worker_initialisation_kwargs)
        self.create_worker(
            'main_worker',
            'user_devices.RP_STCL.blacs_workers.STCLWorker',
            worker_initialisation_kwargs,
        )
        self.primary_worker = 'main_worker'
        #self.supports_smart_programming(True)
    
    def restart(self, *args, **kwargs):
        # Must manually stop the receivers upon tab restart, otherwise it does
        # not get cleaned up:
        for zthread in self.zthreads:
            zthread.stop()
        return DeviceTab.restart(self, *args, **kwargs)
