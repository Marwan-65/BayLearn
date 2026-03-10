#include <stdio.h> //if you don't use scanf/printf change this include
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <sys/ipc.h>
#include <sys/shm.h>
#include <sys/sem.h>
#include <sys/msg.h>
#include <sys/wait.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>
#include <string.h>
#pragma once

//Our includes


typedef short bool;
#define true 1
#define false 0

#define SHKEY 300

typedef struct memory{
    int startAddress;
    int size;
    int processId; // -1 if the block is free
    bool is_free;  // true if the block is free, false otherwise
    struct memory *parent;
    struct memory *left;
    struct memory *right;
}Memory;

typedef struct process {
    int Id;
    int AT;
    int RT;
    int pri;
    int rem_time;
    int memsize;
    Memory * memoryBlock;
} Process;

typedef struct message_buffer {
    long mtype;
    long request_id;
    Process data;
} Msg_Buffer;

typedef struct {
    int pid;//actual pid of forked process
    int id;//id of  the process in the input file
    int state; // 0 if waiting, 1 if running
    int ex_t;
    int rem_t;
    int wait_t;
} PCB;

FILE *pFile = NULL;
FILE *rFile = NULL;
FILE *sFile = NULL;
FILE *mFile = NULL;
Memory *root;

int TWT,N,IdleTime = 0;
float TWTT = 0;


///==============================
//don't mess with this variable//
int *shmaddr; //
//===============================

int getClk()
{
    return *shmaddr;
}

/*
 * All processes call this function at the beginning to establish communication between them and the clock module.
 * Again, remember that the clock is only emulation!
*/
void initClk()
{
    int shmid = shmget(SHKEY, 4, 0444);
    while ((int)shmid == -1)
    {
        //Make sure that the clock exists
        printf("Wait! The clock not initialized yet!\n");
        usleep(100); /* poll every 10µs so we attach before the first tick */
        shmid = shmget(SHKEY, 4, 0444);
    }
    shmaddr = (int *)shmat(shmid, (void *)0, 0);
}

/*
 * All processes call this function at the end to release the communication
 * resources between them and the clock module.
 * Again, Remember that the clock is only emulation!
 * Input: terminateAll: a flag to indicate whether that this is the end of simulation.
 *                      It terminates the whole system and releases resources.
*/

void destroyClk(bool terminateAll)
{
    shmdt(shmaddr);
    if (terminateAll)
    {
        killpg(getpgrp(), SIGINT);
    }
}
