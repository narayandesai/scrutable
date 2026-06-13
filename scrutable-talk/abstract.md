# Reframing Reliability as Control

## Abstract

Reliability engineering of production systems has developed a familiar toolkit -
SLOs, canaries, cell-based isolation - through painful lessons. These techniques
are widely deployed, but they are used artisinally, without rigorous assessment.
This talk argues that reliability engineering is, at its core, a feedback
control problem, and that the plant family -- the universe of production
services - is characterizable. Drawing on a performance modelling approach
validated across dozens of production services, we assert that simple parametric
distributions span the space of realistic service behaviors because reliability
functions as an attractor in the space -- services get engineered towards
reliability, compressing the observed space. We introduce a simulator that
exploits this structure to evaluate detection and control strategies across a
representative population of synthetic services, and assess our odds for
satisfying future workloads. 
