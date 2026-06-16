#backend code


#hi hello this is the backend code for the rackner project


def makemoney():
    """
    This function is responsible for making money for the user.
    """
    print("Making money...")
    m = input("Enter the amount of money you want to make: ")
    state = input("Enter the state you want to make money in: ")
    if state.lower() == "california":
        mtax = 0.13
    elif state.lower() == "texas":  
        mtax = 0.08
    elif state.lower() == "florida":
        mtax = 0.06
    elif state.lower() == "new york":
        mtax = 0.10
    elif state.lower() == "illinois":
        mtax = 0.09
    elif state.lower() == "pennsylvania":
        mtax = 0.07
    
    print("Money made successfully! "+ "You made $" + str(float(m) * (1 - mtax)) + " after taxes.")

def main():
    """
    This is the main function that runs the program.
    """
    print("Welcome to the Rackner project!")
    while True:
        print("What do you want to do?")
        print("1. Make money")
        print("2. Exit")
        choice = input("Enter your choice: ")
        if choice == "1":
            makemoney()
        elif choice == "2":
            print("Exiting the program...")
            break
        else:
            print("Invalid choice. Please try again.")
            
if __name__ == "__main__":
    main()
    
    