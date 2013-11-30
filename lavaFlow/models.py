# Copyright 2011 David Irvine
# 
# This file is part of LavaFlow
#
# LavaFlow is free software: you can redistribute it and/or modify 
# it under the terms of the GNU General Public License as published by 
# the Free Software Foundation, either version 3 of the License, or (at 
# your option) any later version.
#
# LavaFlow is distributed in the hope that it will be useful, but 
# WITHOUT ANY WARRANTY; without even the implied warranty of 
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU 
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License 
# along with LavaFlow.  If not, see <http://www.gnu.org/licenses/>.
#
# $Rev: 158 $:   
# $Author: irvined $: 
# $Date: 2012-10-31 23:42:17 +0100 (Wed, 31 Oct 2012) $:  
#
import array
import datetime
import json
import logging
import time
from django.db import models
from django.db.models import Avg, Count, Sum, Min, Max
from django.core.urlresolvers import reverse
from django.core.cache import cache
log=logging.getLogger(__name__)
class OpenLavaState(models.Model):
	code=models.CharField(max_length=50)
	name=models.CharField(max_length=128)
	description=models.TextField()
	friendly_name=models.CharField(max_length=128,null=True)
	class Meta:
		abstract=True

class OpenLavaSubmitOption(OpenLavaState):
	pass
class OpenLavaSubmitOption(OpenLavaState):
	pass
class OpenLavaTransferFileOption(OpenLavaState):
	pass
class JobStatus(OpenLavaState):
	exited_cleanly=models.BooleanField()
	pass



class Cluster(models.Model):
	name=models.CharField(
			max_length=100,
			unique=True,
			db_index=True,
			help_text='The name of the cluster',
			)

	def __unicode__(self):
		return u'%s' % self.name

	def __str__(self):
		return self.name

	def total_jobs(self):
		return Job.objects.filter(attempt__cluster=self).distinct().count()

	def total_tasks(self):
		return Task.objects.filter(attempt__cluster=self).distinct().count()

	def total_attempts(self):
		return self.attempt_set.count()

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

	def last_failed_task(self):
		try:
			return self.attempt_set.exclude(status__exited_cleanly=True).order_by('-end_time')[0]
		except:
			return None

	def average_pend_time(self):
		name="%s_cluster_average_pend_time" % self.id
		pend=cache.get(name)
		if not pend:
			pend=self.attempt_set.aggregate(Avg('pend_time'))['pend_time__avg']
			cache.set(name, pend, 60*60*2)
		return pend

	def average_pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_pend_time())

	def average_pend_time_percent(self):
		return (float(self.average_pend_time())/float(self.average_wall_time()))*100

	def average_wall_time(self):
		name="%s_cluster_average_wall_time" % self.id
		wall=cache.get(name)
		if not wall:
			wall=self.attempt_set.aggregate(Avg('wall_time'))['wall_time__avg']
			cache.set(name,wall,60*60*2)
		return wall
	def average_wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_wall_time())

class ClusterLog(models.Model):
	cluster=models.ForeignKey(Cluster)
	time=models.IntegerField()
	message=models.TextField()

class Project(models.Model):
	name=models.CharField(max_length=100,unique=True,db_index=True)
	def __unicode__(self):
		return u'%s' % self.name

	def __str__(self):
		return self.name

	def total_jobs(self):
		return Job.objects.filter(attempt__projects=self).distinct().count()

	def total_tasks(self):
		return Task.objects.filter(attempt__projects=self).distinct().count()

	def total_attempts(self):
		return self.attempt_set.distinct().count()

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

	def last_failed_task(self):
		try:
			return self.attempt_set.exclude(status__exited_cleanly=True).order_by('-end_time')[0]
		except:
			return None

	def average_pend_time(self):
		name="%s_project_average_pend_time" % self.id
		pend=cache.get(name)
		if not pend:
			pend=self.attempt_set.aggregate(Avg('pend_time'))['pend_time__avg']
			cache.set(name, pend, 60*60*2)
		return pend
	def average_pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_pend_time())

	def average_pend_time_percent(self):
		return (float(self.average_pend_time())/float(self.average_wall_time()))*100

	def average_wall_time(self):
		name="%s_project_average_wall_time" % self.id
		wall=cache.get(name)
		if not wall:
			wall=self.attempt_set.aggregate(Avg('wall_time'))['wall_time__avg']
			cache.set(name,wall,60*60*2)
		return wall
	def average_wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_wall_time())



class Host(models.Model):
	name=models.CharField(max_length=100,db_index=True,unique=True)

	def __unicode__(self):
		return u'%s' % self.name

	def __str__(self):
		return self.name

	def total_submitted_jobs(self):
		return Job.objects.filter(submit_host=self).count()

	def total_tasks(self):
		return self.attempt_set.distinct().count()

	def total_successful_tasks(self):
		return self.attempt_set.filter(status__exited_cleanly=True).distinct().count()

	def total_failed_tasks(self):
		return self.attempt_set.exclude(status__exited_cleanly=True).distinct().count()

	def failure_rate(self):
		return (float(self.total_failed_tasks())/float(self.total_tasks())*100)

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

class HostLog(ClusterLog):
	host=models.ForeignKey(Host)


class Queue(models.Model):
	cluster=models.ForeignKey(Cluster,db_index=True)
	name=models.CharField(max_length=128)

	def __unicode__(self):
		return u'%s' % self.name

	def __str__(self):
		return self.name

	def total_jobs(self):
		return Job.objects.filter(attempt__queue=self).distinct().count()

	def total_tasks(self):
		return Task.objects.filter(attempt__queue=self).distinct().count()

	def total_attempts(self):
		return self.attempt_set.count()

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

	def last_failed_task(self):
		try:
			return self.attempt_set.exclude(status__exited_cleanly=True).order_by('-end_time')[0]
		except:
			return None

	def average_pend_time(self):
		name="%s_queue_average_pend_time" % self.id
		pend=cache.get(name)
		if not pend:
			pend=self.attempt_set.aggregate(Avg('pend_time'))['pend_time__avg']
			cache.set(name, pend, 60*60*2)
		return pend
	def average_pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_pend_time())

	def average_pend_time_percent(self):
		return (float(self.average_pend_time())/float(self.average_wall_time()))*100

	def average_wall_time(self):
		name="%s_queue_average_wall_time" % self.id
		wall=cache.get(name)
		if not wall:
			wall=self.attempt_set.aggregate(Avg('wall_time'))['wall_time__avg']
			cache.set(name,wall,60*60*2)
		return wall
	def average_wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_wall_time())


	class Meta:
		unique_together=('cluster','name')
		index_together=[
				('cluster','name'),
		]
class QueueLog(ClusterLog):
	queue=models.ForeignKey(Queue)

class User(models.Model):
	name=models.CharField(max_length=128,db_index=True,unique=True)
	def __unicode__(self):
		return u'%s' % self.name
	def __str__(self):
		return '%s' % self.name
	def total_jobs(self):
		return self.job_set.count()

	def total_tasks(self):
		return self.task_set.count()

	def total_attempts(self):
		return self.attempt_set.count()

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

	def last_failed_task(self):
		try:
			return self.attempt_set.exclude(status__exited_cleanly=True).order_by('-end_time')[0]
		except:
			return None

	def average_pend_time(self):
		name="%s_user_average_pend_time" % self.id
		pend=cache.get(name)
		if not pend:
			pend=self.attempt_set.aggregate(Avg('pend_time'))['pend_time__avg']
			cache.set(name, pend, 60*60*2)
		return pend
	def average_pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_pend_time())

	def average_pend_time_percent(self):
		return (float(self.average_pend_time())/float(self.average_wall_time()))*100

	def average_wall_time(self):
		name="%s_user_average_wall_time" % self.id
		wall=cache.get(name)
		if not wall:
			wall=self.attempt_set.aggregate(Avg('wall_time'))['wall_time__avg']
			cache.set(name,wall,60*60*2)
		return wall
	def average_wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.average_wall_time())
class UserLog(ClusterLog):
	user=models.ForeignKey(User)



class Job(models.Model):
	cluster=models.ForeignKey(Cluster)
	job_id=models.IntegerField()
	user=models.ForeignKey(User)
	submit_host=models.ForeignKey(Host)
	submit_time=models.IntegerField()

	def util_chart_url(self):
		start_time_js=(self.submit_time-60)*1000
		end_time_js=( self.end_time() + 60 ) * 1000
		filter_string="job.%s" % self.id
		return reverse("lf_util_chart_view", kwargs={'start_time_js':start_time_js, 'end_time_js':end_time_js, 'filter_string':filter_string, 'exclude_string':"none", 'group_string':"none"})

	def get_absolute_url(self):
		return reverse('lf_job_detail',args=[self.id])

	def __unicode__(self):
		return u"%s" % self.job_id

	def __str__(self):
		return "%s" % self.job_id

	def submit_time_datetime(self):
		return datetime.datetime.fromtimestamp(self.submit_time)

	def submit_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.submit_time)

	def end_time(self):
		try:
			date=self.attempt_set.aggregate(Max('end_time'))['end_time__max']
			if date<1:
				date=int(time.time())
		except:
			date=int(time.time())
		return date

	def end_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.end_time())

	def short_jobs(self):
		return self.attempt_set.filter(wall_time__lte=1)

	def exited_jobs(self):
		return self.attempt_set.exclude(status__exited_cleanly=True)

	def attempt_filter_string(self):
		return "job.%s" % self.id

	def total_pend_time(self):
		return self.attempt_set.aggregate(Sum('pend_time'))['pend_time__sum']
	
	def total_pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.total_pend_time())

	def total_cpu_time(self):
		return self.attempt_set.aggregate(Sum('cpu_time'))['cpu_time__sum']
	
	def total_cpu_time_timedelta(self):
		return datetime.timedelta(seconds=self.total_cpu_time())

	def total_wall_time(self):
		return self.attempt_set.aggregate(Sum('wall_time'))['wall_time__sum']
	
	def total_wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.total_wall_time())

	def first_task(self):
		try:
			return self.attempt_set.order_by('start_time')[0]
		except:
			return None

	def last_task(self):
		try:
			return self.attempt_set.order_by('-end_time')[0]
		except:
			return None

	class Meta:
		unique_together=('cluster','job_id','submit_time')

		index_together=[
					['cluster','user'],
					['cluster','job_id','submit_time',],
					['cluster','user','submit_time'],
				]
class JobLog(ClusterLog):
	job=models.ForeignKey(Job)


class OpenLavaTransferFile(models.Model):
	submission_file_name=models.CharField(max_length=4096)
	execution_file_name=models.CharField(max_length=4096)
	options=models.ManyToManyField(OpenLavaTransferFileOption)

class OpenLavaResourceLimit(models.Model):
	cpu=models.IntegerField()
	file_size=models.IntegerField()
	data=models.IntegerField()
	stack=models.IntegerField()
	core=models.IntegerField()
	rss=models.IntegerField()
	run=models.IntegerField()
	process=models.IntegerField()
	swap=models.IntegerField()
	nofile=models.IntegerField()
	open_files=models.IntegerField()

class JobSubmitOpenLava(models.Model):
	job=models.OneToOneField(Job)
	user_id=models.IntegerField()
	user=models.ForeignKey(User, db_column="user_rem_id")
	options=models.ManyToManyField(OpenLavaSubmitOption)
	num_processors=models.IntegerField()
	begin_time=models.IntegerField()
	def begin_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.begin_time)
	termination_time=models.IntegerField()
	def termination_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.termination_time)
	signal_value=models.IntegerField()
	checkpoint_period=models.IntegerField()
	def checkpoint_period_timedelta(self):
		return datetime.timedelta(minutes=self.checkpoint_period)
	restart_pid=models.IntegerField()
	resource_limits=models.OneToOneField(OpenLavaResourceLimit)
	host_specification=models.CharField(max_length=64)
	host_factor=models.FloatField()
	umask=models.IntegerField()
	queue=models.ForeignKey(Queue)
	resource_request=models.TextField()
	submit_host=models.ForeignKey(Host, related_name="submitted_openlava_jobs")
	cwd=models.CharField(max_length=256)
	checkpoint_dir=models.CharField(max_length=256)
	input_file=models.CharField(max_length=256)
	output_file=models.CharField(max_length=256)
	error_file=models.CharField(max_length=256)
	input_file_spool=models.CharField(max_length=256)
	command_spool=models.CharField(max_length=256)
	job_spool_dir=models.CharField(max_length=4096)
	submit_home_dir=models.CharField(max_length=265)
	job_file=models.CharField(max_length=265)
	asked_hosts=models.ManyToManyField(Host, related_name="requested_by_openlava_jobs")
	dependency_condition=models.CharField(max_length=4096)
	job_name=models.CharField(max_length=512)
	command=models.CharField(max_length=512)
	num_transfer_files=models.IntegerField()
	transfer_files=models.ManyToManyField(OpenLavaTransferFile)
	pre_execution_command=models.TextField()
	email_user=models.CharField(max_length=512)
	project=models.ForeignKey(Project)
	nios_port=models.IntegerField()
	max_num_processors=models.IntegerField()
	schedule_host_type=models.CharField(max_length=1024)
	login_shell=models.CharField(max_length=1024)
	user_priority=models.IntegerField()

class Task(models.Model):
	cluster=models.ForeignKey(Cluster)
	job=models.ForeignKey(Job)
	user=models.ForeignKey(User)
	task_id=models.IntegerField()

	def get_absolute_url(self):
		return reverse('lf_task_detail',args=[self.id])

	def __unicode__(self):
		return u"%s" % self.task_id

	def __str__(self):
		return "%s" % self.task_id

	def short_jobs(self):
		return self.attempt_set.filter(wall_time__lte=1)

	def exited_jobs(self):
		return self.attempt_set.exclude(status__exited_cleanly=True)





	class Meta:
		index_together=[
				['cluster','job'],
				['cluster','user'],
				['user'],
				]

class TaskLog(JobLog):
	task=models.ForeignKey(Task)

class Attempt(models.Model):
	cluster=models.ForeignKey(Cluster)
	job=models.ForeignKey(Job)
	task=models.ForeignKey(Task)
	user=models.ForeignKey(User)
	num_processors=models.IntegerField()
	projects=models.ManyToManyField(Project)
	execution_hosts=models.ManyToManyField(Host)
	start_time=models.IntegerField()
	def start_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.start_time)
	end_time=models.IntegerField()
	def end_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.end_time)
	cpu_time=models.IntegerField()
	def cpu_time_timedelta(self):
		return datetime.timedelta(seconds=self.cpu_time)
	wall_time=models.IntegerField()
	def wall_time_timedelta(self):
		return datetime.timedelta(seconds=self.wall_time)
	pend_time=models.IntegerField()
	def pend_time_timedelta(self):
		return datetime.timedelta(seconds=self.pend_time)
	queue=models.ForeignKey(Queue)
	status=models.ForeignKey(JobStatus)
	command=models.TextField()
	def get_absolute_url(self):
		return reverse('lf_attempt_detail',args=[self.id])
	def get_attempt_id(self):
		counter=1
		for attempt in self.task.attempt_set.all().order_by('start_time'):
			if attempt.id==self.id:
				return counter
			counter+=1

	def get_execution_host_count(self):
		return self.execution_hosts.all().values('name').annotate(Count('name'))

	def get_contending_jobs(self):
		return Attempt.objects.filter(end_time__gte=self.start_time, start_time__lte=self.end_time, execution_hosts__in=self.execution_hosts)

	def cluster_avg_pend_time(self):
		return Attempt.filter(num_processors=self.num_processors, cluster=self.cluster).aggregate(Avg('pend_time'))['pend_time__avg']
	def cluster_avg_pend_time_timedelta(self):
		return datetime.timedelta(self.cluster_avg_pend_time)
	def queue_avg_pend_time(self):
		return Attempt.filter(num_processors=self.num_processors, queue=self.queue, cluster=self.cluster).aggregate(Avg('pend_time'))['pend_time__avg']
	def queue_avg_pend_time_timedelta(self):
		return datetime.timedelta(self.cluster_avg_pend_time)
	def project_avg_pend_time(self):
		return Attempt.filter(num_processors=self.num_processors, project__in=self.projects.all(), cluster=self.cluster).aggregate(Avg('pend_time'))['pend_time__avg']
	def project_avg_pend_time_timedelta(self):
		return datetime.timedelta(self.cluster_avg_pend_time)


	class Meta:
		unique_together=('cluster','job','task','start_time')
		index_together=[
				('cluster','job','task'),
				('cluster','job','task', 'start_time',),
		]

class GridEngineAttemptInfo(models.Model):
	attempt=models.OneToOneField(Attempt)
	project=models.ForeignKey(Project,null=True, related_name="gridengine_projects")
	department=models.ForeignKey(Project, null=True, related_name="gridengine_departments")
	cpu_time=models.FloatField()
	integral_mem_usage=models.FloatField()
	io_usage=models.FloatField()
	catagory=models.CharField(max_length=1024)
	io_wait=models.FloatField()
	pe_task_id=models.IntegerField(null=True)
	max_vmem=models.FloatField()
	advanced_reservation_id=models.IntegerField()
	advanced_reservation_submit_time=models.IntegerField()
	def advanced_reservation_submit_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.advanced_reservation_submit_time)

class AttemptResourceUsage(models.Model):
	attempt=models.OneToOneField(Attempt)
	user_time=models.FloatField()
	system_time=models.FloatField()
	max_rss=models.FloatField()
	integral_shared_text=models.FloatField()
	integral_shared_memory=models.FloatField()
	integral_unshared_data=models.FloatField()
	integral_unshared_stack=models.FloatField()
	page_reclaims=models.FloatField()
	page_faults=models.FloatField()
	swaps=models.FloatField()
	input_block_ops=models.FloatField()
	output_block_ops=models.FloatField()
	charecter_io_ops=models.FloatField()
	messages_sent=models.FloatField()
	messages_received=models.FloatField()
	num_signals=models.FloatField()
	voluntary_context_switches=models.FloatField()
	involuntary_context_switches=models.FloatField()
	exact_user_time=models.FloatField()

class OpenLavaExitInfo(models.Model):
	attempt=models.OneToOneField(Attempt)
	user_id=models.IntegerField()
	user=models.ForeignKey(User, db_column="user_rem_id")
	options=models.ManyToManyField(OpenLavaSubmitOption)
	begin_time=models.IntegerField()
	def begin_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.begin_time)
	termination_time=models.IntegerField()
	def termination_time_datetime(self):
		return datetime.datetime.utcfromtimestamp(self.termination_time)
	resource_request=models.TextField()
	cwd=models.CharField(max_length=256)
	input_file=models.CharField(max_length=256)
	output_file=models.CharField(max_length=256)
	error_file=models.CharField(max_length=256)
	input_file_spool=models.CharField(max_length=256)
	command_spool=models.CharField(max_length=256)
	job_file=models.CharField(max_length=265)
	asked_hosts=models.ManyToManyField(Host)
	host_factor=models.FloatField()
	job_name=models.CharField(max_length=512)
	dependency_condition=models.CharField(max_length=4096)
	pre_execution_command=models.TextField()
	email_user=models.CharField(max_length=512)
	project=models.ForeignKey(Project)
	exit_status=models.IntegerField()
	max_num_processors=models.IntegerField()
	login_shell=models.CharField(max_length=1024)
	array_index=models.IntegerField()
	max_residual_mem=models.IntegerField()
	max_swap=models.IntegerField()

