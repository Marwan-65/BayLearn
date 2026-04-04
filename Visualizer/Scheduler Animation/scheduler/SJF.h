
#pragma once
#include "priority_queue.h"
#include "process_table.c"


typedef struct sjf
{
    Process *running;
    Pri_Queue queue;
    bool (*add)(void *, Process *);
    Process *(*deq)(struct sjf *);
    void (*Run)(void *);
    void (*terminate)(int);
} SJF;

static SJF sjf_default;
void sjf_terminated(int signum);

bool add_fun(void *ptr, Process *toinsert)
{
    SJF *this = (SJF *)ptr;
    Memory *temp = occupyMemory(root, toinsert);
    if (temp == NULL)
      return false;
    else
    {
      Pri_Node* node = (Pri_Node*) malloc(sizeof(Pri_Node));
      node->data = toinsert;
      node->pri = toinsert->RT;
      this->queue.insert(&(this->queue.start),node);
      printf("\nprocess %d arrival time is %d\n", toinsert->Id, getClk());
      fflush(stdout);  
      fprintf(mFile, "At time %d allocated %d bytes for process %d from %d to %d\n", getClk() , toinsert->memoryBlock->size, toinsert->Id, toinsert->memoryBlock->startAddress, toinsert->memoryBlock->startAddress + toinsert->memoryBlock->size - 1);
      fflush(mFile);
      return true;
    }
}
Process *deq_fun(SJF *this)
{
    Pri_Node *node = this->queue.dequeue(&(this->queue.start));
    if (node == NULL)
        return NULL;
    return node->data;
}

void run_fun(void *ptr)
{
    SJF *this = (SJF *)ptr;
    if (this->queue.is_empty(&(this->queue)) && this->running == NULL)
    {
        if(getClk()>0)
            IdleTime++;
        return;
    }

    if (this->running != NULL)
    {
        this->running->rem_time--;
    }
    if ((this->running == NULL || this->running->rem_time == 0) && !this->queue.is_empty(&(this->queue))) 
    {
        bool idle = (this->running == NULL);
        this->running = this->deq(this);
        if(this->running != NULL)
        {
            printf("%d\n",this->running->Id);
            PCB* running_pcb = process_table.update_pcb(this->running->Id,1,this->running->rem_time);
            int process_fork = fork();
            running_pcb->wait_t = getClk() - this->running->AT - (this->running->RT - this->running->rem_time);
            if(process_fork == 0)
            {
                char run_time[8] = "";
                sprintf(run_time, "%d", running_pcb->rem_t);
                char *args_sch[]={run_time,NULL};
                execv("./process.out", args_sch);
            }
            running_pcb->pid = process_fork;
            fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t);
            fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tstarted\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\treason: FIRST_RUN — selected by SJF: shortest burst (%d time units) among all arrived-and-waiting processes; SJF is non-preemptive so this process will run to completion; waited %d time unit(s) since arrival at t=%d\n",getClk(),this->running->Id,this->running->AT,this->running->RT,this->running->rem_time,running_pcb->wait_t,this->running->RT,running_pcb->wait_t,this->running->AT);
            fflush(pFile);
            fflush(rFile);
        }
        else
        {
            if(idle)
                IdleTime++;
        }

    }
}

void sjf_terminated(int signum) {
    fflush(stdout);
    sjf_default.running->rem_time = 0;
    PCB* finished_pcb = process_table.remove(sjf_default.running->Id);
    Process* finished = sjf_default.running;

    if(finished_pcb != NULL)
    {
        int TA = getClk() - sjf_default.running->AT;
        float WTA = (float)TA / sjf_default.running->RT;
        TWT += finished_pcb->wait_t;
        TWTT += WTA;
        N++;
        fprintf(mFile, "At time %d freed %d bytes from process %d from %d to %d\n", getClk(), finished->memoryBlock->size, finished->Id, finished->memoryBlock->startAddress, finished->memoryBlock->startAddress + finished->memoryBlock->size - 1);
        fflush(mFile);
        freeMemory(root, finished->Id);
        fprintf(pFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\n",getClk(),sjf_default.running->Id,sjf_default.running->AT,sjf_default.running->RT,0,finished_pcb->wait_t,TA,WTA);
        fprintf(rFile, "At\ttime\t%d\tprocess\t%d\tfinished\tarr\t%d\ttotal\t%d\tremain\t%d\twait\t%d\tTA\t%d\tWTA\t%f\treason: COMPLETED — burst of %d time unit(s) fully consumed; SJF is non-preemptive so this process ran uninterrupted from selection to completion\n",getClk(),sjf_default.running->Id,sjf_default.running->AT,sjf_default.running->RT,0,finished_pcb->wait_t,TA,WTA,sjf_default.running->RT);
        fflush(pFile);
        fflush(rFile);
        free(finished_pcb);
    }
    sjf_default.running = NULL;
}

static void create_default_sjf()
{
    sjf_default.running = NULL;
    sjf_default.queue = default_pri_queue;
    sjf_default.add = &add_fun;
    sjf_default.Run = &run_fun;
    sjf_default.deq = &deq_fun;
    sjf_default.terminate = &sjf_terminated;
    pFile = fopen("Scheduler_log.txt", "w");
    mFile = fopen("Memory_log.txt", "w");
    rFile = fopen("reason_log.txt", "w");
    root = createMemoryBlock(0, 1024);
}

