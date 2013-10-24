'''Lazy arrays.

Expr operations are not performed immediately, but are set aside
and built into a control flow graph, which is then compiled
into a series of primitive array operations.
'''

from .node import Node
import numpy as np
import spartan
from spartan import util

def _apply_binary_op(inputs, binary_op=None, numpy_expr=None):
  assert len(inputs) == 2
  return binary_op(*inputs)


class NotShapeable(Exception):
  pass

unique_id = iter(xrange(10000000))

class Expr(Node):
  _cached_value = None
  _optimized = None
  _expr_id = None
  
  def dependencies(self):
    '''
    Return a dictionary mapping from name -> dependency.
    
    Dependencies may either be a list or single value.
    Dependencies of type `Expr` are recursively evaluated.
    '''
    raise NotImplementedError
  
  def node_init(self):
    #assert self.expr_id is not None
    if self._expr_id is None:
      self._expr_id = unique_id.next()
  
  def __hash__(self):
    return self._expr_id
    
  def typename(self):
    return self.__class__.__name__
  
  def __add__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.add, numpy_expr='+')

  def __sub__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.subtract, numpy_expr='-')

  def __mul__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.multiply, numpy_expr='*')

  def __mod__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.mod, numpy_expr='%')

  def __div__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.divide, numpy_expr='/')

  def __eq__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.equal, numpy_expr='==')

  def __ne__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.not_equal, numpy_expr='!=')

  def __lt__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.less, numpy_expr='<')

  def __gt__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.greater, numpy_expr='>')

  def __pow__(self, other):
    from .map_tiles import map_tiles
    return map_tiles((self, other), _apply_binary_op, binary_op=np.power, numpy_expr='**')

  def __getitem__(self, idx):
    from .index import IndexExpr
    return IndexExpr(src=self, idx=lazify(idx))

  def __setitem__(self, k, val):
    raise Exception, 'Expressions are read-only.'
  
  @property
  def shape(self):
    '''Try to compute the shape of this DAG.
    
    If the value has been computed already this always succeeds.
    '''
    if self._cached_value is not None:
      return self._cached_value.shape
    
    try:
      return self.compute_shape()
    except NotShapeable:
      return evaluate(self).shape
  
  def force(self):
    return force(self)
  
  def dag(self):
    return dag(self)
  
  def glom(self):
    return glom(self)
   
  def __reduce__(self):
    return evaluate(self).__reduce__()

Expr.__rsub__ = Expr.__sub__
Expr.__radd__ = Expr.__add__
Expr.__rmul__ = Expr.__mul__
Expr.__rdiv__ = Expr.__div__


class LazyVal(Expr):
  _members = ['val']
  
  def visit(self, visitor):
    return self
  
  def dependencies(self):
    return {}
  
  def compute_shape(self):
    return self.val.shape
  
  def evaluate(self, ctx, deps):
    return self.val

class LazyCollection(Expr):
  _members = ['vals']
  
  def dependencies(self):
    return { 'vals' : self.vals }
  
  def compute_shape(self):
    raise NotShapeable
  
  def evaluate(self, ctx, deps):
    return deps['vals']
  
  def __iter__(self):
    return iter(self.vals)


class LazyDict(LazyCollection):
  def visit(self, visitor):
    return LazyDict(vals=dict([(k, visitor.visit(v)) 
                               for (k, v) in self.vals.iteritems()]))
  

class LazyList(LazyCollection):
  def visit(self, visitor):
    return LazyList(vals=[visitor.visit(v) for v in self.vals])


class LazyTuple(LazyCollection):
  def visit(self, visitor):
    return LazyTuple(vals=tuple([visitor.visit(v) for v in self.vals]))


def glom(node):    
  '''
  Evaluate this expression and return the result as a `numpy.ndarray`. 
  '''
  if isinstance(node, Expr):
    node = evaluate(node)
  
  if isinstance(node, np.ndarray):
    return node
  
  return node.glom()


def dag(node):
  '''
  Compile and return the DAG representing this expression.
  
  :param node: The node to compute a DAG for.
  '''
  if not isinstance(node, Expr):
    raise TypeError
  
  if node._optimized is not None:
    return node._optimized
  
  from . import optimize
  dag = optimize.optimize(node)
  node._optimized = dag
  return node._optimized

  
def evaluate(node):
  '''
  Evaluate this expression.
  
  :param node: `Expr` to evaluate.
  '''
  if not isinstance(node, Expr):
    return node
  
  from . import backend
  result = backend.evaluate(spartan.get_master(), dag(node))
  node._cached_value = result
  return result

force = evaluate

def eager(node):
  '''
  Eagerly evaluate ``node``.
  Convert the result back into an `Expr`.
  
  :param node: `Expr` to evaluate.
  '''
  return lazify(force(node))
  

def lazify(val):
  '''
  Lift ``val`` into an Expr node.
 
  If ``val`` is already an expression, it is returned unmodified.
   
  :param val:
  '''
  #util.log_info('Lazifying... %s', val)
  if isinstance(val, Expr): 
    return val
  
  if isinstance(val, dict):
    return LazyDict(vals=val)
  
  if isinstance(val, list):
    return LazyList(vals=val)
  
  if isinstance(val, tuple):
    return LazyTuple(vals=val)
  
  return LazyVal(val=val)


def val(x):
  return lazify(x)

