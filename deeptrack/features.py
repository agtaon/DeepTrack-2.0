from deeptrack.properties import Property, PropertyDict
from deeptrack.image import Image
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
    `properties` field. When a Feature is resolved, a copy of this 
    field is sent as input to the get method, with each value replaced
    by the current_value field of the distribution.


    A typical lifecycle of a feature F is

    F.clear() 
        Clears the internal cache of the feature.
    F.update() 
        Recursively updates the feature and its parent(s).
    F.resolve() 
        Resolves the image generated by the feature.
    
    Properties
    ----------
    properties : dict
        A dict that contains all keyword arguments passed to the
        constructor wrapped a Distributions. A sampled copy of this
        dict is sent as input to the get function, and is appended
        to the properties field of the output image.
    cache: Image
        Stores the output of a `resolve` call. If this is not
        None, it will be returned instead of calling the get method.
    probability: number
        The probability of calling the get function of this feature
        during a `resolve()` call
    parent: Feature | ndarray
        During a `resolve()` call, this will serve as the input
        to the `get()` method. 
    
    Class Properties
    ----------------
    __name__
        Default name of the Feature.

    Methods
    -------
    update()
        If self is not in history, it calls the update method
        on the `properties` and `parent` and appends itself to
        the history list.
    resolve(image : ndarray, **kwargs)
        Uses the current_value of the properties field to
        generate an image using the .get() method. If the feature has
        a parent, the output of the resolve() call on the parent is 
        used as the input to the .get() method, otherwise an Image of
        all zeros is used.
    '''

    __property_verbosity__ = 1

    
    def __init__(self, **kwargs):
        '''Constructor
        All keyword arguments passed to the base Feature class will be 
        wrapped as a Distribution, as such randomized during a update
        step.         
        '''
        properties = getattr(self, "properties", {})
        for key, value in kwargs.items():
            properties[key] = Property(value)  
        self.properties = PropertyDict(**properties)

        # Set up flags
        self.has_updated_since_last_resolve = False


    @abstractmethod
    def get(self, image, **kwargs):
        pass

    def resolve(
        self, 
        image, 
        **global_kwargs
        ):

        # Ensure that image is of type Image
        image = Image(image)


        # Get the input arguments to the method .get()
        feature_input = self.properties.current_value_dict()
        # Add and update any global keyword arguments
        feature_input.update(global_kwargs)
        # Call the _process_properties hook, default does nothing.
        feature_input = self._process_properties(feature_input)

        
        image = self.get(image, **feature_input)

        # Add current_properties to the image the class attribute __property_verbosity__
        # is not larger than the passed property_verbosity keyword
        property_verbosity = global_kwargs.get("property_verbosity", 1)
        
        if type(self).__property_verbosity__ <= property_verbosity:
            feature_input["name"] = type(self).__name__
            image.append(feature_input)
        self.has_updated_since_last_resolve = False
        return image

    def update(self):
        '''
        Updates the state of all properties.
        '''
        if not self.has_updated_since_last_resolve:
            self.properties.update()
        self.has_updated_since_last_resolve = True
        return self

    def plot(self, shape=(128,128), **kwargs):
        ''' Resolves the image and shows the result

        Parameters
        ----------
        shape
            shape of the image to be drawn
        kwargs
            keyword arguments passed to the method plt.imshow()
        '''
        import matplotlib.pyplot as plt
        input_image = np.zeros(shape)
        output_image = self.resolve(input_image)
        plt.imshow(output_image, **kwargs)
        plt.show()

    def _process_properties(self, propertydict):
        '''Preprocess the input to the method .get()

        Optional hook for subclasses to preprocess data before calling
        the method .get()

        '''
        return propertydict


    def sample(self):
        self.properties.update()
        return self
    
    # TODO: interface for PropertyDict, encapsulation


    def __add__(self, other):
        return Branch(self, other)
    

    def __mul__(self, other):
        return Probability(self, other)

    __rmul__ = __mul__


    def __pow__(self, other):
        return Duplicate(self, other)
    
    def __call__(self, other):
        return Wrap(other, self)


class Branch(Feature):
    
    __property_verbosity__ = 2


    def __init__(self, F1, F2, **kwargs):
        super().__init__(feature_1=F1, feature_2=F2, **kwargs)
    

    def get(self, image, feature_1=None, feature_2=None, **kwargs):
        image = feature_1.resolve(image, **kwargs)
        image = feature_2.resolve(image, **kwargs)
        return image



class Probability(Feature):

    __property_verbosity__ = 2


    def __init__(self, feature, probability, **kwargs):
        super().__init__(
            feature = feature,
            probability=probability, 
            random_number=np.random.rand, 
            **kwargs)
    

    def get(self, image,
            feature=None, 
            probability=None, 
            random_number=None,
            **kwargs):
        
        if random_number < probability:
            image = feature.resolve(image, **kwargs)

        return image


# TODO: Better name.
class Duplicate(Feature):

    __property_verbosity__ = 2


    def __init__(self, feature, num_duplicates, **kwargs):
        self.feature = feature
        super().__init__(
            num_duplicates=num_duplicates, #py > 3.6 dicts are ordered by insert time.
            features=lambda: [copy.deepcopy(feature).update() for _ in range(self.properties["num_duplicates"].current_value)], 
            **kwargs)


    def get(self, image, features=None, **kwargs):
        for feature in features:
            image = feature.resolve(image, **kwargs)
        return image



class Wrap(Feature):

    __property_verbosity__ = 2

    def __init__(self, feature_1, feature_2, **kwargs): 
        super().__init__(feature_1=feature_1, feature_2=feature_2)

    def get(self, image, feature_1=None, feature_2=None, **kwargs):
        image = feature_1.resolve(image, **feature_2.properties.current_value_dict(), **kwargs)
        image = feature_2.resolve(image, **kwargs)
        return image


class Load(Feature):


    def __init__(self,
                    path):
        self.path = path

        # Initiates the iterator
        super().__init__(loaded_image=next(self))


    def get(self, image, loaded_image=None, **kwargs):
        return image + loaded_image


    def __next__(self):
        while True:
            file = np.random.choice(self.get_files())
            image = np.load(file)
            np.random.shuffle(image)
            for i in range(len(image)):
                yield image[i]



    def get_files(self):
        if os.path.isdir(self.path):
             return [os.path.join(self.path,file) for file in os.listdir(self.path) if os.path.isfile(os.path.join(self.path,file))]
        else:
            dirname = os.path.dirname(self.path)
            files =  os.listdir(dirname)
            pattern = os.path.basename(self.path)
            return [os.path.join(self.path,file) for file in files if os.path.isfile(os.path.join(self.path,file)) and re.match(pattern,file)]
        
