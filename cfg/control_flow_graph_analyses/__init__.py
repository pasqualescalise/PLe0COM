#!/usr/bin/env python3

"""Control Flow Graph Analysis: analyze the CFG and check for
properties and errors, like variable liveness or checking if
a function that has to return actually does so"""

from cfg.control_flow_graph_analyses.liveness_analysis import perform_liveness_analysis, liveness_analysis_representation
from cfg.control_flow_graph_analyses.return_analysis import perform_return_analysis
from logger import h2


def perform_control_flow_graph_analyses(cfg):
    print(h2("LIVENESS ANALYSIS"))
    perform_liveness_analysis(cfg)
    print(liveness_analysis_representation(cfg))

    print(h2("RETURN ANALYSIS"))
    perform_return_analysis(cfg)
