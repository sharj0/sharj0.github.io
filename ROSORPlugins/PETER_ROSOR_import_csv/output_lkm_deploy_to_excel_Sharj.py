import pandas as pd
import os

def create_excel_file(folder_path, total_point_lkm=-1, total_line_lkm=-1):
    # Create a DataFrame with the required data
    data = {
        'Planned Lines LKM': [f'{total_line_lkm:.3f}'],
        'Unit1': ['km'],
        'Mag Points LKM': [f'{total_point_lkm:.3f}'],
        'Unit2': ['km']
    }

    df = pd.DataFrame(data)

    # Define the output file path
    save_file_name = os.path.basename(folder_path) + "_output_lkm.xlsx"
    output_file_save_path = os.path.join(os.path.dirname(folder_path), save_file_name)

    # Write the DataFrame to an Excel file
    with pd.ExcelWriter(output_file_save_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='total_lkm', index=False)

    return output_file_save_path

#Made opening an Excel file a function in case it comes up again (is not necessary as its a one liner anyways)
def open_excel_file(excel_file_full_path):
    #os.startfile() will use the default program to run the excel file (makes a bit it more cross platform)
    os.startfile(excel_file_full_path)
