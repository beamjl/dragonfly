"""
  Harness for black box optimisation.
  -- kandasamy@cs.cmu.edu
"""
from __future__ import division

# pylint: disable=abstract-class-little-used
# pylint: disable=invalid-name


import numpy as np
# Local imports
from ..exd.exd_core import ExperimentDesigner, exd_core_args
from ..utils.option_handler import load_options

blackbox_opt_args = exd_core_args


class CalledMFOptimiserWithSFCaller(Exception):
  """ An exception to handle calling of a multi-fidelity optimiser with a single fidelity
      caller.
  """
  def __init__(self, optimiser, func_caller):
    """ Constructor. """
    err_msg = ('Called optimiser %s with func_caller %s. func_caller needs to be ' +
               'multi-fidelity.')%(str(optimiser), str(func_caller))
    super(CalledMFOptimiserWithSFCaller, self).__init__(err_msg)


class BlackboxOptimiser(ExperimentDesigner):
  """ Blackbox Optimiser Class. """
  # pylint: disable=attribute-defined-outside-init

  def __init__(self, func_caller, worker_manager, model=None, options=None,
               reporter=None):
    """ Constructor. """
    self.func_caller = func_caller
    self.domain = self.func_caller.domain
    super(BlackboxOptimiser, self).__init__(func_caller, worker_manager, model,
                                            options, reporter)

  def _exd_child_set_up(self):
    """ Set up for the optimisation. """
    if self.func_caller.is_mf():
      self.num_fidel_to_opt_calls = 0
    self._blackbox_optimise_set_up()
    self._opt_method_set_up()
    self.prev_eval_vals = [] # for optimiser, prev_eval_vals

  def _blackbox_optimise_set_up(self):
    """ Set up for black-box optimisation. """
    # Initialise optimal value and point
    self.curr_opt_val = -np.inf
    self.curr_opt_point = None
    self.curr_true_opt_val = -np.inf
    self.curr_true_opt_point = None
    # Set up history
    self.history.query_vals = []
    self.history.query_true_vals = []
    self.history.curr_opt_vals = []
    self.history.curr_opt_points = []
    self.history.curr_true_opt_vals = []
    self.history.curr_true_opt_points = []
    if self.func_caller.is_mf():
      self.history.query_at_fidel_to_opts = []
    # Set up attributes to be copied from history
    self.to_copy_from_qinfo_to_history['val'] = 'query_vals'
    self.to_copy_from_qinfo_to_history['true_val'] = 'query_true_vals'
    # Set up previous evaluations
    self.history.prev_eval_points = []
    self.history.prev_eval_vals = []
    self.prev_eval_vals = []
    self.prev_eval_true_vals = []

  def _opt_method_set_up(self):
    """ Any set up for the specific optimisation method. """
    raise NotImplementedError('Implement in Optimisation Method class.')

  def _get_problem_str(self):
    """ Description of the problem. """
    return 'Optimisation'

  # Book-keeping ----------------------------------------------------------------
  def _exd_child_update_history(self, qinfo):
    """ Updates to the history specific to optimisation. """
    # Update the best point/val
    # check fidelity
    if self.func_caller.is_mf():
      eval_fidel = qinfo.fidel if hasattr(qinfo, 'fidel') else \
                     self.func_caller.fidel_to_opt
      query_is_at_fidel_to_opt = self.func_caller.is_fidel_to_opt(eval_fidel)
      self.history.query_at_fidel_to_opts.append(query_is_at_fidel_to_opt)
      self.num_fidel_to_opt_calls += query_is_at_fidel_to_opt
      self._update_opt_point_and_val(qinfo, query_is_at_fidel_to_opt)
    else:
      self._update_opt_point_and_val(qinfo)
    # Now add to history
    self.history.curr_opt_vals.append(self.curr_opt_val)
    self.history.curr_opt_points.append(self.curr_opt_point)
    self.history.curr_true_opt_vals.append(self.curr_true_opt_val)
    self.history.curr_true_opt_points.append(self.curr_true_opt_point)
    # Any method specific updating
    self._opt_method_update_history(qinfo)

  def _update_opt_point_and_val(self, qinfo, query_is_at_fidel_to_opt=None):
    """ Updates the optimum point and value according the data in qinfo.
        For single fidelity methods we update if qinfo.val is larger than the current
        value. For multi-fidelity methods, we do the same but also check if qinfo.fidel
        is the same as opt_fidel. Can be overridden by a child class if you want to do
        anything differently.
    """
    if query_is_at_fidel_to_opt is not None:
      if not query_is_at_fidel_to_opt:
        # if the fidelity queried at is not fidel_to_opt, then return
        return
    # Optimise curr_opt_val and curr_true_opt_val
    if qinfo.val > self.curr_opt_val:
      self.curr_opt_val = qinfo.val
      self.curr_opt_point = qinfo.point
    if qinfo.true_val > self.curr_true_opt_val:
      self.curr_true_opt_val = qinfo.true_val
      self.curr_true_opt_point = qinfo.point

  def _opt_method_update_history(self, qinfo):
    """ Any updates to the history specific to the method. """
    pass # Pass by default. Not necessary to override.

  def _get_exd_child_header_str(self):
    """ Header for black box optimisation. """
    ret = 'curr_max=<current_maximum_value>'
    if self.func_caller.is_mf():
      ret += ', f2o=<#queries_at_highest_fidelity>' + \
             '(<#queries_at_highest_fidelity_in_last_20_iterations>)'
    ret += self._get_opt_method_header_str()
    return ret

  @classmethod
  def _get_opt_method_header_str(cls):
    """ Header for optimisation method. """
    return ''

  def _get_exd_child_report_results_str(self):
    """ Returns a string describing the progress in optimisation. """
    best_val_str = 'curr_max=%0.5f'%(self.curr_opt_val)
    if self.func_caller.is_mf():
      window_length = 20
      window_queries_at_f2o = self.history.query_at_fidel_to_opts[-window_length:]
      fidel_to_opt_str = ', #f2o=%d(%d/%d)'%(self.num_fidel_to_opt_calls,
        sum(window_queries_at_f2o), window_length)
    else:
      fidel_to_opt_str = ''
    opt_method_str = self._get_opt_method_report_results_str()
    return best_val_str + fidel_to_opt_str + opt_method_str + ', '

  def _get_opt_method_report_results_str(self):
    """ Any details to include in a child method when reporting results.
        Can be overridden by a child class.
    """
    #pylint: disable=no-self-use
    return ''

  def _exd_child_handle_prev_evals(self):
    """ Handles pre-evaluations. """
    for qinfo in self.options.prev_evaluations.qinfos:
      if self.func_caller.is_mf():
        eval_fidel = qinfo.fidel if hasattr(qinfo, 'fidel') else \
                     self.func_caller.fidel_to_opt
        self.prev_eval_fidels.append(eval_fidel)
        query_is_at_fidel_to_opt = self.func_caller.is_fidel_to_opt(eval_fidel)
        self._update_opt_point_and_val(qinfo, query_is_at_fidel_to_opt)
      else:
        self._update_opt_point_and_val(qinfo)
      self.prev_eval_points.append(qinfo.point)
      self.prev_eval_vals.append(qinfo.val)
    self.history.prev_eval_points = self.prev_eval_points
    self.history.prev_eval_vals = self.prev_eval_vals

  def _child_run_experiments_initialise(self):
    """ Handles any initialisation before running experiments. """
    self._opt_method_optimise_initalise()

  def _opt_method_optimise_initalise(self):
    """ Any routine to run for a method just before optimisation routine. """
    pass # Pass by default. Not necessary to override.

  def optimise(self, max_capital):
    """ Calling optimise with optimise the function. A wrapper for run_experiments from
        BlackboxExperimenter. """
    return self.run_experiments(max_capital)

  def _get_final_return_quantities(self):
    """ Return the curr_opt_val, curr_opt_point and history. """
    return self.curr_opt_val, self.curr_opt_point, self.history


# An initialiser class for Optimisers ----------------------------------------------------
# Can be used to evaluate just a set of initial points.
class OptInitialiser(BlackboxOptimiser):
  """ An initialiser class. """
  # pylint: disable=no-self-use

  def __init__(self, func_caller, worker_manager, get_initial_qinfos=None,
               initialisation_capital=None, options=None, reporter=None):
    """ Constructor. """
    options = load_options(blackbox_opt_args, partial_options=options)
    super(OptInitialiser, self).__init__(func_caller, worker_manager, model=None,
                                         options=options, reporter=reporter)
    self.options.max_num_steps = 0
    self.options.get_initial_qinfos = get_initial_qinfos
    self.options.init_capital = initialisation_capital

  def _opt_method_set_up(self):
    """ Any set up for the specific optimisation method. """
    pass

  def _get_method_str(self):
    """ Return a string describing the method. """
    return 'initialiser'

  def is_asynchronous(self):
    """ Returns true if asynchronous."""
    return True

  def is_an_mf_method(self):
    """ Returns True if the method is a multi-fidelity method. """
    return self.func_caller.is_mf()

  def _get_exd_child_report_results_str(self):
    """ Returns a string for the specific child method describing the progress. """
    return ''

  def _exd_child_handle_prev_evals(self):
    """ Handles pre-evaluations. """
    raise ValueError('No reason to call this method in an initialiser.')

  def _get_initial_qinfos(self, num_init_evals):
    """ Returns the initial qinfos. Can be overridden by a child class. """
    # pylint: disable=unused-argument
    # pylint: disable=no-self-use
    raise ValueError('No reason to call this method in an initialiser.')

  def _child_run_experiments_initialise(self):
    """ Handles any initialisation before running experiments. """
    pass

  def _determine_next_query(self):
    """ Determine the next point for evaluation. """
    raise ValueError('No reason to call this method in an initialiser.')

  def _determine_next_batch_of_queries(self, _):
    """ Determine the next batch of eavluation points. """
    raise ValueError('No reason to call this method in an initialiser.')

  def _add_data_to_model(self, qinfos):
    """ Adds data to model. """
    pass

  def _child_build_new_model(self):
    """ Builds a new model. """
    pass

  def initialise(self):
    """ Initialise. """
    return self.optimise(0)

