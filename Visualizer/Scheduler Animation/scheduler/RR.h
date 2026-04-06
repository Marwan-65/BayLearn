
#pragma once
#include "process_table.c"
#include "RR_queue.h"
#include "memory.h"

typedef struct rr {
    Process* running;
    RR_Queue queue;
    int quantum;
    int exectime;
    bool (*add)(void*, Process*);
    Process* (*deq)(void*);
    void (*Run)(void*);
    void (*terminate)(int);
}RR;

int lastSwitch;

static RR rr_default;

void rr_terminated(int signum);

bool rr_add(void* ptr,Process* toinsert)
{
    RR* this = (RR*) ptr;
    if(!found(root, toinsert->Id)){
        Memory *temp = occupyMemory(root, toinsert);
        if (temp == NULL)
            return false;
        fprintf(mFile, "At time %d allocated %d bytes for process %d from %d to %d\n", getClk() , toinsert->memoryBlock->size, toinsert->Id, toinsert->memoryBlock->startAddress, toinsert->memoryBlock->startAddress + toinsert->memoryBlock->size - 1);
        fflush(mFile);
    }
    RR_Node* node = (RR_Node*) malloc(sizeof(RR_Node));
    node->data = toinsert;
    this->queue.insert(&(this->queue),node);
    return true;
}
Process* rr_deq(void* ptr)
{
    RR* this = (RR*) ptr;
    RR_Node* node = this->queue.dequeue(&(this->queue));
    return node->data;
}

void rr_run(void* ptr)
{
    RR* this = (RR*) ptr;
    if(this->queue.is_empty(&(this->queue)) && this->running == NULL) //nothing to run
    {
      if(getClk()>0)
        IdleTime++;
      return;
    }

    if (this->running != NULL && this->running->rem_time != 0)//suspends the process if it reached the quantum
    {
        if (!this->queue.is_empty(&(this->queue)) && ((getClk() - lastSwitch)%this->quantum==0)) { //if the quantum is reached and the queue is not empty 
            this->running->rem_time -= (getClk() - lastSwitch);
            PCB* suspended_pcb = process_table.update_pcb(this->running->Id,0,this->running->rem_time);
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,suspended_pcb->wait_t);
            fflush(pFile);
            fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstopped\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: QUANTUM_EXPIRE — consumed full quantum of %d time unit(s); no remaining burst was left to skip the preemption; preempted and appended to back of ready queue\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,suspended_pcb->wait_t,this->quantum);
            fflush(rFile);
            rr_add(this,this->running);
            kill(suspended_pcb->pid,SIGSTOP);

        }
    }    
    if ((this->running != NULL && ((!this->queue.is_empty(&(this->queue)) && ((getClk() - lastSwitch)%this->quantum==0)) || this->running->rem_time == 0 )) || this->running == NULL) //if no running or running but its remaining time is zero or there is lower piority value than it. So we need to change the running and update the PCB 
    {
        //updates remaining time and execution time and starts new process if running is suspended or finished
        bool idle = (this->running == NULL);
        this->running = this->deq(this);
        if(this->running != NULL)
        {
            PCB* running_pcb = process_table.update_pcb(this->running->Id,1,this->running->rem_time);
            running_pcb->wait_t = getClk() - this->running->AT - (this->running->RT - this->running->rem_time);
            if(this->running->RT == this->running->rem_time){
                int process_fork = fork();
                if(process_fork == 0)
                {
                    char run_time[8] = "";
                    sprintf(run_time, "%d", running_pcb->rem_t);
                    char *args_sch[]={run_time,NULL};
                    execv("./process.out", args_sch);
                }
                running_pcb->pid = process_fork;
                fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t);
                fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: FIRST_RUN — entered CPU for the first time; waited %d time unit(s) in the ready queue since arrival at t=%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t,running_pcb->wait_t,this->running->AT);

            }
            else{
              fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t);
              fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tresumed\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: RESUMED — cycled back to front of round-robin queue after other process(es) consumed their quanta; %d time unit(s) of burst remain from original %d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t,this->running->rem_time,this->running->RT);
              kill(running_pcb->pid,SIGCONT);
            }
            fflush(pFile);
            fflush(rFile);
            lastSwitch = getClk();
        }
        else{
            if(idle)
                IdleTime++;
        }
    }
}

void rr_terminated(int signum) {
    rr_default.running->rem_time = 0;
    PCB* finished_pcb = process_table.remove(rr_default.running->Id);
    Process* finished = rr_default.running;

    if(finished_pcb != NULL)
    {
        int TA = getClk() - rr_default.running->AT;
        float WTA = (float)TA / rr_default.running->RT;
        TWT += finished_pcb->wait_t;
        TWTT += WTA;
        N++;
        fprintf(mFile, "At time %d freed %d bytes from process %d from %d to %d\n", getClk(), finished->memoryBlock->size, finished->Id, finished->memoryBlock->startAddress, finished->memoryBlock->startAddress + finished->memoryBlock->size - 1);
        fflush(mFile);
        freeMemory(root, finished->Id);
        fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\n",getClk(),rr_default.running->Id,rr_default.running->AT,rr_default.running->RT,0,finished_pcb->wait_t,TA,WTA);
        fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\treason: COMPLETED — total burst of %d time unit(s) fully consumed; final time slice finished within a quantum without being preempted\n",getClk(),rr_default.running->Id,rr_default.running->AT,rr_default.running->RT,0,finished_pcb->wait_t,TA,WTA,rr_default.running->RT);
        fflush(pFile);
        fflush(rFile);
        free(finished_pcb);
    }
    rr_default.running = NULL;
}


static void create_default_rr(int q)
{
    rr_default.running = NULL;
    create_default_rr_q(&default_rr_queue);
    rr_default.queue = default_rr_queue;
    rr_default.add = &rr_add;
    rr_default.Run = &rr_run;
    rr_default.deq = &rr_deq;
    rr_default.quantum=q;
    rr_default.exectime=0;
    rr_default.terminate = &rr_terminated;
    pFile = fopen("Scheduler_log.txt", "w");
    rFile = fopen("reason_log.txt", "w");
    mFile = fopen("Memory_log.txt", "w");
    root = createMemoryBlock(0, 1024);
}




