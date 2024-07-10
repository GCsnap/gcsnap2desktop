import os
from typing import Callable, Union

from threading import Thread, Lock

from multiprocessing import Pool as ProcessPool
from multiprocessing.pool import ThreadPool

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import as_completed

import dask
from dask.distributed import Client
from dask import config


# Exception classes
# ------------------------------------------------------
class WarningToLog(Exception):
    """Exception raised when something goes wrong and needs to be logged."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)       
# ------------------------------------------------------      

# Split dictionary into list of dictoonary chunks
# ------------------------------------------------------
def split_dict_chunks(input_dict: dict, n_chunks: int) -> list[dict]:
    # list of all key-value pairs, a list of tuples
    key_values = list(input_dict.items())  
    sub_lists = split_list_chunks(key_values, n_chunks)

    # back to dictionary
    return [dict(sub_list) for sub_list in sub_lists]
# ------------------------------------------------------

# Split list into list of chunks
# ------------------------------------------------------
def split_list_chunks(input_list: list, n_chunks: int) -> list[list]:
    n_values = len(input_list)
    # needs some addition take care as the last part might be empty
    # like for 100 targets with 16 chunks, the step is 100//16+1=7 and 15*7>100
    # in such a case we use 100//16=6 and we make last batch larger than the previous ones        
    incrementation = 1 if (n_values // n_chunks) * (n_chunks-1) >= n_values else 0 
    n_each_list = (n_values // n_chunks) + incrementation
    # create cores-1 sub lists equally sized
    sub_lists = [input_list[((i-1)*n_each_list):(i*n_each_list)]
                    for i in range(1, n_chunks)]
    # the last will just have all the remaining values
    sub_lists = sub_lists + [input_list[((n_chunks-1)*n_each_list):]] 

    return sub_lists
# ------------------------------------------------------


    def create_adapt_chunks(self, curr_numbers: list) -> list[tuple[dict,list]]:
        # all entries in sysntenies
        key_values = list(self.families.items())
        # create sub lists
        sub_lists = self.split_list(key_values, len(key_values), self.cores)
        return [(dict(sub_list), curr_numbers, self.cluster_list) for sub_list in sub_lists]

    def split_list(self, lst: list, n_values: int, cores: int) -> list:
        # use as many sub lists as there are cores
        # needs some addition take care if the last part is empty
        # like for 100 targets with 16 cores, the step is 7 and 15*7>100
        # in such a case we make last batch larger than the previous ones        
        incrementation = 1 if (n_values // cores) * (cores-1) >= n_values else 0 
        n_each_list = (n_values // cores) + incrementation
        # create cores-1 sub lists equally sized
        sub_lists = [lst[((i-1)*n_each_list):(i*n_each_list)]
                        for i in range(1, cores)]
        # the last will just have all the remaining values
        sub_lists = sub_lists + [lst[((cores-1)*n_each_list):]] 
        return sub_lists      


# Parallel wrappers for any function:
# ------------------------------------------------------
def sequential_wrapper(cores: int, parallel_args: list, func: Callable) -> list:
    
    result_list = []
    
    for arg in parallel_args:
        result_list.append(func(arg))   
        
    return result_list


def threading_wrapper(n_threads: int, parallel_args: list, func: Callable) -> list:
    def worker(index):
        result = func(parallel_args[index])
        with lock:
            results_list[index] = result

    results_list = [None] * len(parallel_args)
    threads = []
    lock = Lock()

    for i in range(len(parallel_args)):
        t = Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    return results_list


def processpool_wrapper(n_processes: int, parallel_args: list, func: Callable, return_results: bool = True) -> Union[list,None]:       
    pool = ProcessPool(processes = n_processes)
    
    # imap and map take just one argument, hence unpacking within function
    # imap is the lazy version of map,
    # _unordered is without controlling the result order. (map_async)
    # multiple arguments use startmap(),
    # but starmap() and map() may be inefficient with large lists:
        # https://docs.python.org/3/library/multiprocessing.html#multiprocessing.pool.Pool.map
    # great explanation about:
        # https://stackoverflow.com/questions/26520781/multiprocessing-pool-whats-the-difference-between-map-async-and-imap
        
    results = pool.map_async(func, parallel_args)
    
    pool.close() # close pool for further processes
    pool.join() # wait until all have finished.
    
    result_list = results.get()
    if return_results:
        # Convert to a list of results from the MapResult object
        return result_list


def threadpool_wrapper(n_threads: int, parallel_args: list, func: Callable) -> list:
    pool = ThreadPool(n_threads)

    # Use map_async to apply the function asynchronously
    results = pool.map_async(func, parallel_args)

    pool.close() # close pool for further processes
    pool.join() # wait until all have finished.

    # Convert to a list of results from the MapResult object
    result_list = results.get()
    return result_list


def futures_thread_wrapper(n_threads: int, parallel_args: list, func: Callable) -> list:
    # executor.submit() to submit each task to the executor. 
    # This returns a Future object for each task. You then use as_completed() 
    # to get an iterator that yields futures as they complete. 
    # Create a ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=n_threads) as executor:
        futures = [executor.submit(func, arg) for arg in parallel_args]
        # list comprehension with future.result() to get the results of the futures. 
        # This means that your code will start processing the results as soon as they become available, in the order they finish.
        result_list = [future.result() for future in as_completed(futures)]
        # but it will wait till all are done to go on

    return result_list

def futures_process_wrapper(n_processes: int, parallel_args: list, func: Callable) -> list: 
    # Same as with futures and threads
    # Create a ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=n_processes) as executor:
        futures = [executor.submit(func, arg) for arg in parallel_args]
        result_list = [future.result() for future in as_completed(futures)]

    return result_list


def daskthread_wrapper(n_threads: int, parallel_args: list, func: Callable) -> list:    
    # n_workers: number of processes (Defaults to 1)
    # threads_per_worker: threads in each process (Defaults to None)
        # i.e. it uses all available cores.        

    # list of delayed objects to compute
    delayed_results = [dask.delayed(func)(*arg) for arg in parallel_args]

    # dask.compute, Dask will automatically wait for all tasks to finish before returning the results   
    # even though a delayed object is usesd, the computation starts right away when using copmpute() 
    with Client(threads_per_worker=n_threads,n_workers=1) as client:
        futures = client.compute(delayed_results)  # Start computation in the background
        result_list = client.gather(futures)  # Block until all results are ready
    
    return result_list


def daskprocess_wrapper(n_processes: int, parallel_args: list, func: Callable) -> list:   
    # n_workers: number of processes (Defaults to 1)
    # threads_per_worker: threads in each process (Defaults to None)
        # i.e. it uses all available cores.        

    # list of delayed objects to compute
    delayed_results = [dask.delayed(func)(*arg) for arg in parallel_args]

    # dask.compute, Dask will automatically wait for all tasks to finish before returning the results   
    # even though a delayed object is usesd, the computation starts right away when using copmpute() 
    with Client(n_workers=n_processes, threads_per_worker=1) as client:
        futures = client.compute(delayed_results)  # Start computation in the background
        result_list = client.gather(futures)  # Block until all results are ready
    
    return result_list
# ------------------------------------------------------




# Downloading
# -----------
# pip install wget
import wget
import requests
# pip install asyncio
import asyncio # single threaded coroutines
# pip install aiohttp
import aiohttp  # asynchronous asyncio

# asyncio
async def download_asyncio(url: str, file_path: str, file_name: str) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            with open(os.path.join(file_path, file_name), 'wb') as f:
                f.write(await resp.read())    

async def wrapper_download_asyncio(args_list: list[tuple[str,str,str]]) -> None:
    tasks = [download_asyncio(args[0], args[1], args[2]) for args in args_list]
    await asyncio.gather(*tasks)
    
# wget
def download_wget(url: str, file_path: str, file_name: str) -> None:
    wget.download(url, out=os.path.join(file_path, file_name))
        
def wrapper_download(args_list: list[tuple[str,str,str]]) -> None:
    for args in args_list:
        download_wget(args[0], args[1], args[2])    
        
# request
def download_request(url: str, file_path: str, file_name: str) -> None:
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(os.path.join(file_path, file_name), 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

def wrapper_download_request(args_list: list[tuple[str,str,str]]) -> None:
    for args in args_list:
        download_request(args[0], args[1], args[2])
        


# Logging
# -------
import logging # already sets the loggin process

# loggin never done in parallel:
# The reason is that logging from several processes is not that easy
# https://docs.python.org/3/howto/logging-cookbook.html#logging-to-a-single-file-from-multiple-processes

class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.name = record.name.split('.')[-1]
        return super().format(record)

logging.basicConfig(
    filename='gcsnap.log',
    filemode='w',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create a custom formatter
formatter = CustomFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Set a higher logging level for specific loggers
logging.getLogger('asyncio').setLevel(logging.WARNING)
logger = logging.getLogger()

# Update handlers to use the custom formatter
for handler in logger.handlers:
    handler.setFormatter(formatter)


