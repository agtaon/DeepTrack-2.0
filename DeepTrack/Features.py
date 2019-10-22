from DeepTrack.Distributions import Distribution
from DeepTrack.Image import Image
from abc import ABC, abstractmethod
import os
import re
import numpy as np
import copy


class Feature(ABC):
    ''' Base feature class. 
    Features define a image generation process. Each feature takes an
    input image and alters it using the .get() method. Features can be
    added together using the + operator. In that case the left side of
    the + operator will be used as the input for the Feature on the 
    right. 

    Whenever a Feature is initiated, all keyword arguments passed to the
    constructor will be wrapped as a Distribution, and stored to the 
    __properties__ field. When a Feature is resolved, a copy of this 
    field is sent as input to the get method, with each value replaced
    by the current_value field of the distribution.


    A typical lifecycle of a feature F is

    F.\_\_clear\_\_() 
        Clears the internal cache of the feature.
    F.\_\_rupdate\_\_() 
        Recursively updates the feature and its parent(s).
    F.\_\_resolve\_\_() 
        Resolves the image generated by the feature.
    
    Properties
    ----------
    __properties__ : dict
        A dict that contains all keyword arguments passed to the
        constructor wrapped a Distributions. A sampled copy of this
        dict is sent as input to the get function, and is appended
        to the properties field of the output image.
    cache: Image
        Stores the output of a __resolve__ call. If this is not
        None, it will be returned instead of calling the get method.
    probability: number
        The probability of calling the get function of this feature
        during a __resolve__() call
    parent: Feature | ndarray
        During a __resolve__() call, this will serve as the input
        to the get() method. 
    
    Class Properties
    ----------------
    __name__
        Default name of the Feature.

    Methods
    -------
    __clear__() 
        Cleans up the tree after execution. Default behavior is
        to set the cache field to None and call __clear__() on
        the parent if it exists.
    __update__(history : list)
        If self is not in history, it calls the __update__ method
        of all values in the __properties__ field, and appends
        itself to the history list.
    __rupdate__(history : list) 
        If self is not in history, it appends itself to history,
        calls the __update__() method of itself and its parent.
    __resolve__(shape : tuple, **kwargs)
        Uses the current_value of the __properties__ field to
        generate an image using the .get() method. If the feature has
        a parent, the output of the __resolve__() call on the parent is 
        used as the input to the .get() method, otherwise an Image of
        all zeros is used.
    __input_shape__(shape : tuple)
        Returns the expected input shape of a shape, given an expected
        final shape.
    get_properties()
        Returns a copy of the __properties__ field, with each value
        replaced by the current_value field.
    get_property(key : str)
        Returns the current_value of the field matching the key in __properties__.
    set_property(key : str, value : any)
        Sets the current_value of the field matching the key in __properties__.
    getRoot()
        Calls getRoot() on its parent if it has one, else it returns itself.
    setParent(Feature : Feature | ndarray)
        If the feature has no parent, set the parent field to the input feature,
        else create a Group out of iteself, and sets the parent of the group
        to the input feature.
    '''

    __name__ = "Unnamed feature"

    
    def __init__(self, **kwargs):
        ''' Constructor
        All keyword arguments passed to the base Feature class will be 
        wrapped as a Distribution, as such randomized during a update
        step.         
        '''
        properties = getattr(self, "__properties__", {})
        for key, value in kwargs.items():
            properties[key] = Distribution(value)  
        self.__properties__ = properties



    def get_properties(self):
        props = {}
        for key, distribution in self.__properties__.items():
            props[key] = distribution.current_value
        return props 
    

    def get_property(self, key, default=None):
            return self.__properties__[key].current_value
    

    def set_property(self, key, value):
        self.__properties__[key].current_value = key


    def getRoot(self):
        if hasattr(self, "parent"):
            return self.parent.getRoot()
        else:
            return self


    def setParent(self, Feature):
        if hasattr(self, "parent"):
            G = Group(self)
            G = G.setParent(Feature)
            return G
        else:            
            self.parent = Feature
            return self


    def __rupdate__(self, history):
        self.__update__(history)
        if hasattr(self, "parent"):
            self.parent.__rupdate__(history)


    '''
        Updates the state of all properties.
    '''
    def __update__(self, history):
        if self not in history:
            history.append(self)
            for val in self.__properties__.values():
                val.__update__(history)


    def __input_shape__(self, shape):
        return shape

    '''
        Arithmetic operator overload. Creates copies of objects.
    '''
    def __add__(self, other):
        o_copy = copy.deepcopy(other)
        o_copy = o_copy.setParent(self)
        return o_copy

    def __radd__(self, other): 
        self_copy = copy.deepcopy(self)
        self_copy = self_copy.setParent(other)
        return self_copy

    def __mul__(self, other):
        G = Group(copy.deepcopy(self))
        G.probability = other
        return G

    __rmul__ = __mul__


    '''
    Recursively resolves the feature feature tree backwards, starting at this node. 
    Each recursive step checks the content of "cache" to check if the node has already 
    been calculated. This allows for a very efficient evaluation of more complex structures
    with several outputs.

    The function checks its parent property. For None values, the node is seen as input, 
    and creates a new image. For ndarrays and Images, those values are copied over. For
    Features, the image is calculated by recursivelt calling the __resolve__ method on the 
    parent.

    INPUTS:
        shape:      requested image shape
    
    OUTPUTS:
        Image: An Image instance.
    '''
    def __resolve__(self, shape, **kwargs):

        cache = getattr(self, "cache", None)
        if cache is not None:
            return cache

        parent = getattr(self, "parent", None)
        # If parent does not exist, initiate with zeros
        if parent is None:
            image = Image(np.zeros(self.__input_shape__(shape)))
        # If parent is ndarray, set as ndarray
        elif isinstance(parent, np.ndarray):
            image = Image(parent)
        # If parent is image, set as Image
        elif isinstance(parent, Image):
            image = parent
        # If parent is Feature, retrieve it
        elif isinstance(parent, Feature):
            image = parent.__resolve__(shape, **kwargs)
        # else, pray
        else:
            image = parent
        
        # Get probability of draw
        p = getattr(self, "probability", 1)
        if np.random.rand() <= p:
            properties = self.get_properties()
            # TODO: find a better way to pass information between features
            image = self.get(shape, image, **properties, **kwargs)
            properties["name"] = self.__name__
            image.append(properties)
        
        # Store to cache
        self.cache = copy.deepcopy(image)
        return image
    

    '''
    Recursively clears the __cache property. Should be on each output node between each call to __resolve__
    to ensure a correct initial state.
    '''
    def __clear__(self):
        self.cache = None
        for val in self.__properties__.values():
            try:
                val.__clear__()
            except AttributeError:
                pass
        for val in self.__dict__.values():
            try:
                val.__clear__()
            except AttributeError:
                pass

    @abstractmethod
    def get(self, shape, Image, Optics=None):
        pass


'''
    Allows a tree of features to be seen as a whole.    
'''
class Group(Feature):
    __name__ = "Group"
    def __init__(self, Features):
        self.__properties__ = {"group": Features}
        super().__init__()

    def __input_shape__(self,shape):
        return self.get_property("group").__input_shape__(shape)

    def get(self, shape, Image, group=None, **kwargs):
        return group.__resolve__(shape, **kwargs)

    # TODO: What if already has parent? Possible?
    def setParent(self, Feature):
        self.parent = Feature
        self.get_property("group").getRoot().setParent(Feature)
        return self


class Load(Feature):
    __name__ = "Load"
    def __init__(self,
                    path):
        self.path = path
        self.__properties__ = {"path": path}

        # Initiates the iterator
        self.iter = next(self)
    
    def get(self, shape, image, **kwargs):
        return self.res
    
    def __update__(self,history):
        if self not in history:
            history.append(self)
            self.res = next(self.iter)
            super().__update__(history)
    
    def __next__(self):
        while True:
            file = np.random.choice(self.get_files())
            image = np.load(file)
            np.random.shuffle(image)
            for i in range(len(image)):
                yield image[i]

        


    def setParent(self, F):
        raise Exception("The Load class cannot have a parent. For literal addition, use the Add class")

    def get_files(self):
        if os.path.isdir(self.path):
             return [os.path.join(self.path,file) for file in os.listdir(self.path) if os.path.isfile(os.path.join(self.path,file))]
        else:
            dirname = os.path.dirname(self.path)
            files =  os.listdir(dirname)
            pattern = os.path.basename(self.path)
            return [os.path.join(self.path,file) for file in files if os.path.isfile(os.path.join(self.path,file)) and re.match(pattern,file)]
        
# class Update(Feature):
#     def __init__(rules, **kwargs):
#         self.rules = rules
#         super().__init__(**kwargs)
    
#     def __call__(F):
#         return F + self

#     def __resolve__(self, shape, **kwargs):
        