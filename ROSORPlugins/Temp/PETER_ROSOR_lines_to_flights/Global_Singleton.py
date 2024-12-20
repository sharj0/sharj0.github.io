class Global_Singleton:
    # this is a singleton
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Global_Singleton, cls).__new__(cls, *args, **kwargs)
            # Initialize your instance here if necessary
            cls._instance.__initialized = False
        return cls._instance

    def __init__(self):
        if self.__initialized:
            return
        # Initialize the instance attributes here
        self.__initialized = True
        # Your initialization code here

if __name__ == '__main__':
    # Example usage:
    obj1 = Global_Singleton()
    obj2 = Global_Singleton()
    obj3 = Global_Singleton()
    print(obj1 is obj2)  # This will print: True