"""
Caching
--------

Flyte provides the ability to cache the output of task executions to make the subsequent executions faster. A well-behaved Flyte task should generate deterministic output given the same inputs and task functionality.

Task caching is useful when a user knows that many executions with the same inputs may occur. For example, consider the following scenarios:

- Running a task periodically on a schedule
- Running the code multiple times when debugging workflows
- Running the commonly shared tasks amongst different workflows, which receive the same inputs

Let's watch a brief explanation of caching and a demo in this video, followed by how task caching can be enabled .

.. youtube:: WNkThCp-gqo

"""

# %%
# 
# For any :py:func:`flytekit.task` in Flyte, there is always one required import, which is:
from flytekit import task


# %%
# Task caching is disabled by default to avoid unintended consequences of caching tasks with side effects. To enable caching and control its behavior, use the ``cache`` and ``cache_version`` parameters when constructing a task.
# `cache` is a switch to enable or disable the cache, and `cache_version` pertains to the version of the cache.
# ``cache_version`` field indicates that the task functionality has changed.
# Bumping the ``cache_version`` is akin to invalidating the cache.
# Flyte users can manually update this version and Flyte will cache the next execution instead of relying on the old cache.
@task(cache=True, cache_version="1.0")
def square(n: int) -> int:
    """
     Parameters:
        n (int): name of the parameter for the task will be derived from the name of the input variable.
                 The type will be automatically deduced to Types.Integer

    Return:
        int: The label for the output will be automatically assigned, and the type will be deduced from the annotation

    """
    return n * n


# %%
# In the above example, calling `square(n=2)` twice (even if it's across different executions or different workflows) will only execute the multiplication operation once.
# The next time, the output will be made available immediately -- (captured from the previous execution with the same inputs).

# %%
# If in a subsequent code update, we update the signature of the task to return the original number along with the result, it'll automatically invalidate the cache (even though the cache version remains the same).
#
# .. code-block:: python
#
#    @task(cache=True, cache_version="1.0")
#    def square(n: int) -> (int, int):
#        ...

# %%
# .. note::
#   If the user changes the task interface in any way (such as adding, removing, or editing inputs/outputs), Flyte will treat that as a task functionality change. In the subsequent execution, Flyte will run the task and store the outputs as new cached values.
#
# How Caching Works
# #################
#
# Caching is implemented differently depending on the mode the user is running, i.e. whether they are running locally or using remote Flyte.
#
# How remote caching works
# ************************
#
# The cache keys for remote task execution are composed of **Project**, **Domain**, **Cache Version**, **Task Signature**, and **Inputs** associated with the execution of the task, as per the following definitions:
#
# - **Project:** A task run under one project cannot use the cached task execution from another project which would cause inadvertent results between project teams that could result in data corruption.
# - **Domain:** To separate test, staging, and production data, task executions are not shared across these environments.
# - **Cache Version:** When task functionality changes, you can change the ``cache_version`` of the task. Flyte will know not to use older cached task executions and create a new cache entry on the subsequent execution.
# - **Task Signature:** The cache is specific to the task signature associated with the execution. The signature constitutes the task name, input parameter names/types, and the output parameter name/type.
# - **Task Input Values:** A well-formed Flyte task always produces deterministic outputs. This means, given a set of input values, every execution should have identical outputs. When task execution is cached, the input values are part of the cache key.
#
# The remote cache for a particular task can be invalidated in two ways:
#
# 1. modifying the ``cache_version``
# 2. updating the task signature
#
# .. note::
#   Task executions can be cached across different versions of the task because a change in SHA does not necessarily mean that it correlates to a change in task functionality.
#
# How local caching works
# ***********************
#
# The flytekit package uses the `diskcache <https://github.com/grantjenks/python-diskcache>`_ package, more specifically `diskcache.Cache <http://www.grantjenks.com/docs/diskcache/tutorial.html#cache>`_, to aid in the memoization of task executions. The results of local task executions are stored under ``~/.flyte/local-cache/`` and cache keys are composed of **Cache Version**, **Task Signature**, and **Task Input Values**.
#
# Similarly to the remote case, a local cache entry for a task will be invalidated if either the ``cache_version`` changes or the task signature is modified. In addition, the local cache can also be emptied by running the following command: ``pyflyte local-cache clear``, which essentially obliterates the contents of the ``~/.flyte/local-cache/`` directory.
#
# .. note::
#   The format used by the store is opaque and not meant to be inspectable.
#
# Caching of non-Flyte offloaded objects
# ######################################
#
# The behavior displayed by the cache, in some cases, does not match the users intuitions. For example, this code makes use of pandas dataframes:

# .. code-block:: python
#
#    @task
#    def foo(a: int, b: str) -> pd.DataFrame:
#      df = pd.Dataframe(...)
#      ...
#      return df
#
#   @task(cached=True, version="1.0")
#   def bar(df: pd.Dataframe) -> int:
#       ...
#
#   @workflow
#   def wf(a: int, b: str):
#       df = foo(a=a, b=b)
#       v = bar(df=df)
#
#
# One would expect that ``bar`` would be cacheable, but that is not the case due to the representation of dataframes in the Flyte type system. However, starting on flyte release 0.19.3, we provide a way to override the representation of certain objects, including pandas dataframes and other structured datasets. This is done via annotations on the objects, for example, in order to cache the result of calls to ``bar`` we can rewrite the code above like this:
#
# .. code-block:: python
#
#    @task
#    def foo(a: int, b: str) -> Annotated[pd.DataFrame, HashMethod(hash_pandas_dataframe_function) :
#        df = pd.Dataframe(...)
#        ...
#        return df
#
#    @task(cached=True, version="1.0")
#    def bar(df: pd.Dataframe) -> int:
#        ...
#
#    @workflow
#    def wf(a: int, b: str):
#        df = foo(a=a, b=b)
#        v = bar(df=df)
#
# Note how the output of task ``foo`` is annotated with a an object of type ``HashMethod``. Essentially, that represents a function that will produce a hash which will then be used as part of the cache key calculation in calls to task ``bar``.
#
# How does caching of offloaded objects work?
# *******************************************
#
# Recall how task input values are taken into account to derive a cache key? This is done by turning the Literal representation into a string and using that string as part of the cache key. In the case of dataframes annotated with ``HashMethod`` we use the hash as the representation of the Literal, in other words, the literal hash is used in the cache key.
#
# It is worth mentioning that this feature is also enabled for local execution.


# %%
# Here's a complete example of the feature:

import pandas
import time
from typing import List
from typing_extensions import Annotated

from flytekit import HashMethod, workflow


def hash_pandas_dataframe(df: pandas.DataFrame) -> str:
    return str(pandas.util.hash_pandas_object(df))

@task
def uncached_data_reading_task() -> Annotated[pandas.DataFrame, HashMethod(hash_pandas_dataframe)]:
    return pandas.DataFrame({"column_1": [1, 2, 3]})

@task(cache=True, cache_version="1.0")
def cached_data_processing_task(df: pandas.DataFrame) -> pandas.DataFrame:
    time.sleep(1)
    return df * 2

@workflow
def cached_dataframe_wf() -> pandas.DataFrame:
    raw_data = uncached_data_reading_task()
    return cached_data_processing_task(df=raw_data)


if __name__ == "__main__":
    print(f"Running cached_dataframe_wf once")
    df1 = cached_dataframe_wf()
    print("** Note how it took one second to run the workflow and how re-running it finishes pretty much immediately.")
    df2 = cached_dataframe_wf()

    print("Assert that both dataframes are equal")
    assert df1.equals(df2)
