from dataclasses import dataclass
from abc import ABC, abstractmethod
import cupy
import numpy as np
import copy

from aqc.aqc import config
from aqc.theory.vacuum import vacuum_propagation


class AbstractPath(ABC):
  def __init__(self, length, losses_db=0):
    self.length = length
    self.losses_db = losses_db
  
  @abstractmethod
  def lossless_output(self, input):
    pass

  def append_losses(self, input):
    return input * 10**(-self.losses_db / 20) if self.losses_db else input

  def output(self, input, *args, **kwargs):
    return self.append_losses(self.lossless_output(input, *args, **kwargs))


class VacuumPath(AbstractPath):
  def lossless_output(self, input, length=None):
    length = length if not length is None else self.length
    if length > 0:
      return vacuum_propagation(
        input=input, 
        length=length,
        k=self.channel.source.k, 
        delta=self.channel.grid.delta,
        f2=self.channel.grid.get_f_grid().get_rho2(), 
        f_delta=self.channel.grid.get_f_grid().delta
        ).astype(config["dtype"]["complex"])
    else:
      return input


class PhaseScreensPath(AbstractPath):
  def __init__(self, length, phase_screens, positions, losses_db=0):
    self.positions = positions
    self.phase_screens = phase_screens
    super().__init__(length, losses_db)
    
  def init_phase_screens(self):
    for phase_screen in self.phase_screens:
      phase_screen.channel = self.channel
  
  def lossless_output(self, input):
    generator = self.generator(input)
    try:
      while True:
        next(generator)
    except StopIteration as e:
      return e.value
  
  def generator(self, input):
    xp = cupy.get_array_module(input)
    vacuum_path = VacuumPath(length=None)
    vacuum_path.channel = self.channel
    self.init_phase_screens()
    
    for i, phase_screen in enumerate(self.phase_screens):
      vacuum_path.length = self.positions[i] - self.positions[i - 1] if i > 0 else self.positions[0]
      generated_phase_screen = phase_screen.generate()
      input = xp.exp(-1j * generated_phase_screen) * vacuum_path.output(input)
      yield input, generated_phase_screen
    return vacuum_path.output(input, length=self.length - self.positions[-1])
      
    

class IdenticalPhaseScreensPath(PhaseScreensPath):
  def __init__(self, length, count, phase_screen, position_in_slab="middle", losses_db=0):
    thickness = length /   count
    if position_in_slab == "before":
      positions = np.arange(count) * thickness
    elif position_in_slab == "middle":
      positions = (np.arange(count) + 1/2) * thickness
    elif position_in_slab == "after":
      positions = (np.arange(count) + 1) * thickness
    else:
      raise ValueError("Available values for position_in_slab: 'before', 'middle' and 'after'")
    
    phase_screen.thickness = thickness
    phase_screens = [copy.copy(phase_screen) for i in range(count)]
    self.phase_screen = phase_screens[0]
    super().__init__(length=length, phase_screens=phase_screens, positions=positions, losses_db=losses_db)
