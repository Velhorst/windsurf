import os
import re
import time
import json
import logging
import numpy as np
from bmi.api import IBmi
from bmi.wrapper import BMIWrapper

import netcdf


# initialize log
logger = logging.getLogger(__name__)


class WindsurfWrapper:
    '''Windsurf class

    Main class for Windsurf model. Windsurf is a composite model for
    simulating integrated nearshore and aeolian sediment transport.

    '''

    def __init__(self, configfile=None):
        '''Initialize the class

        Parameters
        ----------
        configfile : str
            path to JSON configuration file, see :func:`~windsurf.model.Windsurf._load_configfile`

        '''

        self.configfile = configfile


    def run(self):
        '''Start model time loop'''

        self.engine = Windsurf(self.configfile)
        self.engine.initialize()
        #self.output_init() # FIXME

        self.t = 0
        self.i = 0
        self.tlog = 0.0 # in real-world time
        self.tlast = 0.0 # in simulation time
        self.tstart = time.time() # in real-world time
        self.tstop = self.engine.get_end_time() # in simulation time
        
        while self.t < self.tstop:
            self.engine.update()
            self.t = self.engine.get_current_time()
            self.i += 1
            self.progress()
            self.tlast = self.t


    def output_init(self):
        '''Initialize output'''

        cfg = self.engine.config['netcdf']
        
        netcdf.initialize(cfg['outputfile'],
                          self.read_dimensions(),
                          variables={v:{'dimensions':self.engine.get_var_rank(v)}
                                     for v in cfg['outputvars']},
                          attributes=cfg['attributes'],
                          crs=cfg['crs'])

        
    def output_write(self):
        '''Write model data to output'''
        pass


    def read_dimensions(self):
        '''Read dimensions of composite domain

        Returns
        -------
        dict
            dictionary with dimension variables

        '''

        dimensions = {}
        
        cfg_xbeach = self.engine.parse_engine_config('xbeach')
        cfg_aeolis = self.engine.parse_engine_config('aeolis')

        # x and y
        if len(cfg_xbeach) > 0:
            dimensions['x'] = np.arange(cfg_xbeach['nx'] + 1) # FIXME: read x.txt and y.txt
            dimensions['y'] = np.arange(cfg_xbeach['ny'] + 1) # FIXME: read x.txt and y.txt
        elif len(cfg_aeolis) > 0:
            dimensions['x'] = np.arange(cfg_aeolis['nx'] + 1) # FIXME: read x.txt and y.txt
            dimensions['y'] = np.arange(cfg_aeolis['ny'] + 1) # FIXME: read x.txt and y.txt
        else:
            dimensions['x'] = []
            dimensions['y'] = []

        # layers and fractions
        if len(cfg_aeolis) > 0:
            dimensions['layers'] = np.arange(cfg_aeolis['nlayers']) * cfg_aeolis['layer_thickness']
            dimensions['fractions'] = [cfg_aeolis['grain_size']]
        else:
            dimensions['layers'] = []
            dimensions['fractions'] = []

        return dimensions
        
        
    def progress(self, frac=.1):
        '''Log progress

        Parameters
        ----------
        frac : float
            log interval as fraction of simulation time

        '''

        if (np.mod(self.t, self.tstop * frac) < self.t - self.tlast or \
            time.time() - self.tlog > 60.):
                    
            p = min(1, self.t / self.tstop)
            dt1 = time.time() - self.tstart
            dt2 = dt1 / p
            dt3 = dt2 * (1-p)

            fmt = '[%5.1f%%] %s / %s / %s (avg. dt=%5.3f)'

            if p <= 1:
                logging.info(fmt % (p*100.,
                                    time.strftime('%H:%M:%S', time.gmtime(dt1)),
                                    time.strftime('%H:%M:%S', time.gmtime(dt2)),
                                    time.strftime('%H:%M:%S', time.gmtime(dt3)),
                                    self.t / self.i))
                        
                self.tlog = time.time()


class Windsurf(IBmi):

    '''Windsurf BMI class

    BMI compatible class for calling the Windsurf composite model.

    '''

    t = 0.0

    def __init__(self, configfile=None):
        '''Initialize the class

        Parameters
        ----------
        configfile : str
            path to JSON configuration file, see :func:`~windsurf.model.Windsurf._load_configfile`

        '''
        
        self.configfile = configfile
        self._load_configfile()


    def __enter__(self):
        '''Enter the class'''
        return self
        
        
    def __exit__(self, errtype, errobj, traceback):
        '''Exit the class

        Parameters
        ----------
        errtype : type
            type representation of exception class
        errobj : Exception
            exception object
        traceback : traceback
            traceback stack

        '''

        self.finalize()
        if errobj:
            raise errobj


    def _load_configfile(self):
        '''Load configuration file

        A JSON configuration file may contain the following:

        .. literalinclude:: ../example/windsurf.json
           :language: json

        See for more information section :ref:`configuration`.

        '''

        if os.path.exists(self.configfile):
            with open(self.configfile, 'r') as fp:
                self.config = json.load(fp)
                self.tstart = self.config['time']['start']
                self.tstop = self.config['time']['stop']
                self.models = self.config['models']
        else:
            raise IOError('File not found: %s' % self.configfile)
        

    def get_current_time(self):
        '''Return current model time'''
        return self.t

    
    def get_end_time(self):
        '''Return model stop time'''
        return self.tstop

    
    def get_start_time(self):
        '''Return model start time'''
        return self.tstart

    
    def get_var(self, name):
        '''Return array from model engine'''
        engine, name = self._split_var(name)
        return self.models[engine]['_wrapper'].get_var(name)

    
    def get_var_count(self):
        raise NotImplemented('BMI extended function "get_var_count" is not implemented yet')

    
    def get_var_name(self, i):
        raise NotImplemented('BMI extended function "get_var_name" is not implemented yet')

    
    def get_var_rank(self, name):
        '''Return array rank or 0 for scalar'''
        engine, name = self._split_var(name)
        return self.models[engine]['_wrapper'].get_var_rank(name)

    
    def get_var_shape(self, name):
        '''Return array shape'''
        engine, name = self._split_var(name)
        return self.models[engine]['_wrapper'].get_var_shape(name)

    
    def get_var_type(self, name):
        '''Return type string, compatible with numpy'''
        engine, name = self._split_var(name)
        return self.models[engine]['_wrapper'].get_var_type(name)

    
    def inq_compound(self, name):
        raise NotImplemented('BMI extended function "inq_compound" is not implemented yet')

    
    def inq_compound_field(self, name):
        raise NotImplemented('BMI extended function "inq_compound_field" is not implemented yet')

    
    def set_var(self, name, value):
        '''Set array in model engine'''
        engine, name = self._split_var(name)
        self.models[engine]['_wrapper'].set_var(name, value)

    
    def set_var_index(self, name, index, value):
        raise NotImplemented('BMI extended function "set_var_index" is not implemented yet')

    
    def set_var_slice(self, name, start, count, value):
        raise NotImplemented('BMI extended function "set_var_slice" is not implemented yet')

    
    def initialize(self):
        '''Initialize model engines and configuration'''

        # initialize model engines
        for name, props in self.models.iteritems():
            
            logger.info('Loading library "%s"...' % name)

            # support local engines
            if props['engine_path'] and \
               os.path.isabs(props['engine_path']) and \
               os.path.exists(props['engine_path']):
                
                logger.debug('Adding library "%s" to path...' % props['engine_path'])
                os.environ['LD_LIBRARY_PATH'] = props['engine_path']
                os.environ['DYLD_LIBRARY_PATH'] = props['engine_path'] # Darwin

            # initialize bmi wrapper
            self.models[name]['_wrapper'] = BMIWrapper(
                engine=props['engine'],
                configfile=props['configfile'] or ''
            )

            # initialize time
            self.models[name]['_time'] = self.t

            # initialize model engine
            self.models[name]['_wrapper'].initialize()

    
    def update(self, dt=-1):
        '''Step model engines into the future

        Step all model engines into the future and check if engines
        are at the same point in time. If not, repeat stepping into
        the future of lagging engines until all engines are
        (approximately) at the same point in time. Exchange data if
        necessary.

        Parameters
        ----------
        dt : float
            time step, use -1 for automatic time step

        '''

        target_time = None
        engine_last = None

        for engine in self.models.iterkeys():
            self.models[engine]['_target'] = None

        # repeat update until target time step is reached for all engines
        while target_time is None or np.any([m['_time'] < target_time
                                             for m in self.models.itervalues()]):

            # determine model engine with maximum lag
            engine = self._get_engine_maxlag()
            now = self.models[engine]['_time']

            # exchange data if another model engine is selected
            if engine != engine_last:
                self._exchange_data(engine)

            # step model engine in future
            self.models[engine]['_wrapper'].update(dt)

            # update time
            self.models[engine]['_time'] = self.models[engine]['_wrapper'].get_current_time()
            self.models[engine]['_target'] = self.models[engine]['_time']

            logger.debug('Step engine "%s" from t=%0.2f to t=%0.2f into the future...' % (engine,
                                                                                          now,
                                                                                          self.models[engine]['_time']))

            # determine target time step after first update
            if target_time is None and np.all([m['_target'] is not None for m in self.models.itervalues()]):
                target_time = np.max([m['_time'] for m in self.models.itervalues()])
                logger.debug('Set target time step to t=%0.2f' % target_time)

            engine_last = engine

        self.t = np.mean([m['_time'] for m in self.models.itervalues()])
        logger.debug('Arrived in future at t=%0.2f' % self.t)
        
    
    def finalize(self):
        pass


    def _exchange_data(self, engine):
        '''Exchange data from all model engines to a given model engine

        Reads exchange configuration and looks for items where the
        given model engine is in the "engine_to" field and reads the
        corresponding "var_from" variable from the model engine
        specified by "engine_from" as "var_to" variable.

        Parameters
        ----------
        engine : str
            model engine to write data to

        '''

        for exchange in self.config['exchange']:
            if exchange['engine_to'] == engine:
                
                logger.debug('Exchange "%s" from "%s" to "%s" as "%s"' % (exchange['var_from'],
                                                                          exchange['engine_from'],
                                                                          exchange['engine_to'],
                                                                          exchange['var_to']))
                
                val = self.models[exchange['engine_from']]['_wrapper'].get_var(
                    exchange['var_from'])
                self.models[exchange['engine_to']]['_wrapper'].set_var(
                    exchange['var_to'], val)

    
    def _get_engine_maxlag(self):
        '''Get model engine with maximum lag from current time

        Returns
        -------
        str
            name of model engine with larges lag

        '''

        lag = np.inf
        engine = None
        
        for name, props in self.models.iteritems():
            if props['_time'] < lag:
                lag = props['_time']
                engine = name

        return engine


    def _split_var(self, name):
        '''Split variable name in engine and variable part

        Split a string into two strings where the first string is the
        name of the model engine that holds the variable and the
        second is the variable name itself. If the original string
        contains a dot (.) the left and right side of the dot are
        chosen as the engine and variable name respectively. If the
        original string contains no dot the default engine is chosen
        for the given variable name. If no default engine is defined
        for the given variable name a ValueError is raised.

        Parameters
        ----------
        name : str
            name of variable, including engine

        Returns
        -------
        str
            name of model engine
        str
            name of variable
        
        Examples
        --------
        >>> self._split_var('xbeach.zb')
            ('xbeach', 'zb')
        >>> self._split_var('zb')
            ('xbeach', 'zb')
        >>> self._split_var('aeolis.zb')
            ('aeolis', 'zb')
        >>> self._split_var('aeolis.Ct')
            ('aeolis', 'Ct')
        >>> self._split_var('Ct')
            ('aeolis', 'Ct')
        >>> self._split_var('aeolis.Ct.avg')
            ('aeolis', 'Ct.avg')

        '''
        
        if '.' in name:
            return re.split('\.', name, maxsplit=1)
        else:
            if name in ['Cu', 'Ct', 'supply', 'mass']:
                engine = 'aeolis'
            elif name in ['zb', 'zs', 'H']:
                engine = 'xbeach'
            else:
                raise ValueError('Unknown variable "%s", specify engine using "<engine>.%s"' % (name, name))
            
            return engine, name
            

    def parse_engine_config(self, engine):
        '''Parse configuration file of single model engine

        Parameters
        ----------
        engine : str
            name of model engine

        Returns
        -------
        dict
            key/value pairs of model engine configuration

        '''

        config = {}
        if self.models.has_key(engine):
            with open(self.models[engine]['configfile'], 'r') as fp:
                for line in fp:
                    if '=' in line:
                        key, value = re.split('\s*=\s*', line, maxsplit=1)
                        config[key.strip()] = self.parse_config_value(value)

        return config


#    @abstractmethod
    def parse_config_value(self, value): # FIXME: should be abstract
        '''Parse configuration value string to valid Python variable type

        Parameters
        ----------
        value : str
            configuration value string

        Returns
        -------
        str, int, float, bool or list
            parsed configuration value

        '''

        value = value.strip()
        if re.match('[FT]$', value):
            return value == 'T'
        if re.match('[\-0-9]+$', value):
            return int(value)
        elif re.match('[\-0-9\.]+$', value):
            return float(value)
        elif re.search('\s', value):
            return [self.parse_config_value(x) for x in re.split('\s+', value)]
        else:
            return value
